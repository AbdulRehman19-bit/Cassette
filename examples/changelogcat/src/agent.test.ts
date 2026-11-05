import { describe, expect, it } from "vitest";
import { runAgent, type ModelClient, type ToolHost } from "./agent.js";

const host = (calls: string[]): ToolHost => ({
  listTools: async () => [
    { name: "list_pull_requests", inputSchema: { type: "object" } },
    { name: "create_issue", inputSchema: { type: "object" } },
  ],
  callTool: async (name) => {
    calls.push(name);
    return "[]";
  },
  close: async () => {},
});

const scripted = (responses: object[]): ModelClient => {
  let i = 0;
  return { messages: { create: async () => responses[i++] as never } };
};

const input = { repo: "a/b", fromTag: "v1", toTag: "v2" };

describe("runAgent", () => {
  it("calls an allowed tool then returns the final text", async () => {
    const calls: string[] = [];
    const client = scripted([
      { content: [{ type: "tool_use", id: "t1", name: "list_pull_requests", input: { state: "closed" } }] },
      { content: [{ type: "text", text: "## New\n- thing" }] },
    ]);
    const r = await runAgent(input, host(calls), client, { model: "m" });
    expect(calls).toEqual(["list_pull_requests"]);
    expect(r.output).toBe("## New\n- thing");
    expect(r.stoppedByLimit).toBe(false);
  });

  it("refuses tools outside the allowlist", async () => {
    const calls: string[] = [];
    const client = scripted([
      { content: [{ type: "tool_use", id: "t1", name: "create_issue", input: {} }] },
      { content: [{ type: "text", text: "done" }] },
    ]);
    await runAgent(input, host(calls), client, { model: "m" });
    expect(calls).toEqual([]);
  });

  it("stops at the step limit", async () => {
    const loop = { content: [{ type: "tool_use", id: "t", name: "list_pull_requests", input: {} }] };
    const client = scripted(Array(20).fill(loop));
    const r = await runAgent(input, host([]), client, { model: "m", maxSteps: 3 });
    expect(r.stoppedByLimit).toBe(true);
    expect(r.steps).toBe(3);
  });
});
