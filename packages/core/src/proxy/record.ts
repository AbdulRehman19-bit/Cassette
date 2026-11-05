import { appendTrace } from "../trace.js";
import type { ToolBackend } from "./backend.js";

/** Wraps a backend so every tool listing and call is appended to the trace. */
export function recording(backend: ToolBackend, opts: { server: string; tracePath: string }): ToolBackend {
  return {
    async listTools() {
      const tools = await backend.listTools();
      appendTrace(opts.tracePath, {
        type: "tools",
        server: opts.server,
        tools: tools.map((t) => ({ name: t.name, inputSchema: t.inputSchema })),
      });
      return tools;
    },
    async callTool(name, args) {
      const start = Date.now();
      try {
        const result = await backend.callTool(name, args);
        appendTrace(opts.tracePath, {
          type: "tool",
          server: opts.server,
          name,
          args,
          result,
          isError: result.isError === true ? true : undefined,
          ms: Date.now() - start,
        });
        return result;
      } catch (e) {
        appendTrace(opts.tracePath, {
          type: "tool",
          server: opts.server,
          name,
          args,
          result: { content: [{ type: "text", text: String(e) }], isError: true },
          isError: true,
          ms: Date.now() - start,
        });
        throw e;
      }
    },
    close: () => backend.close(),
  };
}
