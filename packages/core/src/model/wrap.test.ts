import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { readTrace } from "../trace.js";
import { maybeWrapModel, wrapModel } from "./wrap.js";

const client = () => ({
  messages: {
    create: async (p: { model: string }) => ({ model: p.model, content: [], usage: { input_tokens: 12, output_tokens: 3 } }),
  },
});

describe("wrapModel", () => {
  it("returns the original response and logs request, response, usage and latency", async () => {
    const dir = await mkdtemp(join(tmpdir(), "model-"));
    const tracePath = join(dir, "t.jsonl");
    const c = wrapModel(client(), { tracePath });
    const res = await c.messages.create({ model: "m1" });
    expect(res.model).toBe("m1");
    const [ev] = readTrace(tracePath);
    expect(ev).toMatchObject({ type: "model", request: { model: "m1" }, usage: { in: 12, out: 3 } });
    expect((ev as { ms: number }).ms).toBeGreaterThanOrEqual(0);
  });

  it("only wraps when CASSETTE_TRACE is set", () => {
    const c = client();
    expect(maybeWrapModel(c, {})).toBe(c);
    expect(maybeWrapModel(c, { CASSETTE_TRACE: "x" })).not.toBe(c);
  });
});
