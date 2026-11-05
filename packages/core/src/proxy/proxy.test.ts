import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { describe, expect, it } from "vitest";
import { readTrace } from "../trace.js";
import type { ToolBackend } from "./backend.js";
import { recording } from "./record.js";
import { serveProxy } from "./server.js";

const fake = (): ToolBackend => ({
  listTools: async () => [{ name: "list_pull_requests", description: "d", inputSchema: { type: "object" } }],
  callTool: async (name, args) => ({ content: [{ type: "text", text: `${name}:${JSON.stringify(args)}` }] }),
  close: async () => {},
});

describe("recording proxy", () => {
  it("forwards tool listing and calls and appends them to the trace", async () => {
    const dir = await mkdtemp(join(tmpdir(), "trace-"));
    const tracePath = join(dir, "t.jsonl");
    const [clientT, serverT] = InMemoryTransport.createLinkedPair();
    await serveProxy(recording(fake(), { server: "github", tracePath }), serverT);
    const client = new Client({ name: "agent", version: "0" });
    await client.connect(clientT);

    const { tools } = await client.listTools();
    expect(tools.map((t) => t.name)).toEqual(["list_pull_requests"]);
    const res = await client.callTool({ name: "list_pull_requests", arguments: { state: "closed" } });
    expect((res.content as { text: string }[])[0]?.text).toBe('list_pull_requests:{"state":"closed"}');

    const events = readTrace(tracePath);
    expect(events.map((e) => e.type)).toEqual(["tools", "tool"]);
    expect(events[1]).toMatchObject({ type: "tool", server: "github", name: "list_pull_requests", args: { state: "closed" } });
    await client.close();
  });
});
