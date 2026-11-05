import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { canonicalArgs, normalize } from "./normalize.js";
import { listCassettes, readScenario, writeCassette } from "./store.js";
import type { Cassette } from "./schema.js";

const sample = (extra: Partial<Cassette> = {}): Cassette => ({
  version: 1,
  scenario: "release-v1.4",
  recordedAt: "2026-11-05T10:00:00.000Z",
  agent: { model: "claude-sonnet-5-5" },
  input: { repo: "acme/widgets" },
  steps: [
    { i: 0, type: "model", request: { id: "msg_01ABCdef123456" }, response: { at: "2026-11-05T10:00:01Z" } },
    { i: 1, type: "tool", server: "github", name: "list_pull_requests", args: { b: 1, a: 2 }, result: { ok: true } },
  ],
  output: "## New",
  toolSchemas: { github: [{ name: "list_pull_requests", inputSchema: {} }] },
  ...extra,
});

describe("normalize", () => {
  it("replaces timestamps, uuids and provider ids and sorts keys", () => {
    const out = normalize({
      z: "at 2026-01-02T03:04:05Z",
      a: "9b2e7c1a-1111-4222-8333-444455556666",
      m: "toolu_01AbCdEfGh",
    });
    expect(Object.keys(out)).toEqual(["a", "m", "z"]);
    expect(out).toEqual({ a: "<id>", m: "<id>", z: "at <timestamp>" });
  });

  it("makes arg key order irrelevant", () => {
    expect(canonicalArgs({ a: 1, b: 2 })).toBe(canonicalArgs({ b: 2, a: 1 }));
  });
});

describe("store", () => {
  it("round-trips and normalizes on write", async () => {
    const dir = await mkdtemp(join(tmpdir(), "cassette-"));
    const path = await writeCassette(dir, sample());
    const raw = await readFile(path, "utf8");
    expect(raw).not.toContain("2026-11-05");
    expect(raw).not.toContain("msg_01ABC");
    const back = await readScenario(dir, "release-v1.4");
    expect(back.recordedAt).toBe("<normalized>");
    expect(back.steps).toHaveLength(2);
  });

  it("writes identical bytes for runs differing only in volatile fields", async () => {
    const dir = await mkdtemp(join(tmpdir(), "cassette-"));
    const p1 = await writeCassette(dir, sample());
    const a = await readFile(p1, "utf8");
    await writeCassette(dir, sample({ recordedAt: "2030-01-01T00:00:00Z" }));
    expect(await readFile(p1, "utf8")).toBe(a);
  });

  it("lists scenarios and tolerates a missing dir", async () => {
    const dir = await mkdtemp(join(tmpdir(), "cassette-"));
    await writeCassette(dir, sample());
    expect(await listCassettes(dir)).toEqual(["release-v1.4"]);
    expect(await listCassettes(join(dir, "nope"))).toEqual([]);
  });

  it("rejects invalid cassettes", async () => {
    const dir = await mkdtemp(join(tmpdir(), "cassette-"));
    await expect(writeCassette(dir, { ...sample(), steps: [{ i: 0, type: "tool" }] } as never)).rejects.toThrow();
  });
});
