import { describe, expect, it } from "vitest";
import { buildCassette } from "../cassette/build.js";
import { replayBackend } from "./backend.js";
import { Matcher } from "./match.js";
import type { TraceEvent } from "../trace.js";

const events: TraceEvent[] = [
  { type: "tools", server: "github", tools: [{ name: "list_pull_requests", inputSchema: { type: "object" } }] },
  { type: "model", request: {}, response: {}, usage: { in: 1, out: 1 } },
  { type: "tool", server: "github", name: "list_pull_requests", args: { state: "closed", per_page: 30 }, result: { content: [{ type: "text", text: "first" }] } },
  { type: "tool", server: "github", name: "list_pull_requests", args: { state: "closed", per_page: 30 }, result: { content: [{ type: "text", text: "second" }] } },
];
const cassette = () => buildCassette(events, { scenario: "s", input: {}, output: "o" });

describe("buildCassette", () => {
  it("orders steps and captures tool schemas", () => {
    const c = cassette();
    expect(c.steps.map((s) => s.type)).toEqual(["model", "tool", "tool"]);
    expect(c.steps.map((s) => s.i)).toEqual([0, 1, 2]);
    expect(c.toolSchemas.github?.[0]?.name).toBe("list_pull_requests");
  });
});

describe("Matcher", () => {
  it("matches exact args regardless of key order and replays repeats in order", () => {
    const m = new Matcher(cassette());
    expect(m.find("github", "list_pull_requests", { per_page: 30, state: "closed" })?.result).toMatchObject({ content: [{ text: "first" }] });
    expect(m.find("github", "list_pull_requests", { state: "closed", per_page: 30 })?.result).toMatchObject({ content: [{ text: "second" }] });
    expect(m.find("github", "list_pull_requests", { state: "closed", per_page: 30 })).toBeUndefined();
  });

  it("falls back to the tolerant match, honouring ignoreArgs", () => {
    const m = new Matcher(cassette(), { ignoreArgs: ["per_page"] });
    expect(m.find("github", "list_pull_requests", { state: "closed", per_page: 100 })).toBeDefined();
  });

  it("does not tolerate changes when tolerance is exact", () => {
    const m = new Matcher(cassette(), { tolerance: "exact", ignoreArgs: ["per_page"] });
    expect(m.find("github", "list_pull_requests", { state: "closed", per_page: 100 })).toBeUndefined();
  });

  it("treats different args as unmatched and reports unused steps", () => {
    const m = new Matcher(cassette());
    expect(m.find("github", "list_pull_requests", { state: "open", per_page: 30 })).toBeUndefined();
    expect(m.unused()).toHaveLength(2);
  });
});

describe("replayBackend", () => {
  it("answers from the cassette and flags unmatched calls as divergence without touching a live server", async () => {
    const diverged: string[] = [];
    const b = replayBackend(cassette(), { server: "github", onDivergence: (d) => diverged.push(d.name) });
    expect((await b.listTools()).map((t) => t.name)).toEqual(["list_pull_requests"]);
    const ok = await b.callTool("list_pull_requests", { state: "closed", per_page: 30 });
    expect(ok.isError).toBeUndefined();
    const bad = await b.callTool("create_issue", { title: "x" });
    expect(bad.isError).toBe(true);
    expect(diverged).toEqual(["create_issue"]);
  });
});
