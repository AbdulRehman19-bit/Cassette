import type { Cassette } from "../cassette/schema.js";
import type { CallResult, ToolBackend } from "../proxy/backend.js";
import { appendTrace } from "../trace.js";
import { Matcher, type MatchOptions } from "./match.js";

export interface ReplayOptions extends MatchOptions {
  server: string;
  /** Where to log the replayed run (same trace format as recording), so it can be diffed. */
  tracePath?: string;
  /** Called with a live call that has no recorded answer. Default: answer with an error. */
  onDivergence?: (d: { server: string; name: string; args: Record<string, unknown> }) => void;
}

/** Answers tool calls from a cassette. Never touches the real server. */
export function replayBackend(cassette: Cassette, opts: ReplayOptions): ToolBackend {
  const matcher = new Matcher(cassette, opts);
  return {
    async listTools() {
      const tools = cassette.toolSchemas[opts.server] ?? [];
      return tools.map((t) => ({ name: t.name, inputSchema: (t.inputSchema ?? { type: "object" }) as Record<string, unknown> }));
    },
    async callTool(name, args): Promise<CallResult> {
      const start = Date.now();
      const hit = matcher.find(opts.server, name, args);
      if (!hit) {
        opts.onDivergence?.({ server: opts.server, name, args });
        const reason = `cassette: no recorded result for ${name}(${JSON.stringify(args)})`;
        if (opts.tracePath) appendTrace(opts.tracePath, { type: "divergence", server: opts.server, name, args, reason });
        return { content: [{ type: "text", text: reason }], isError: true };
      }
      const result = hit.result as CallResult;
      if (opts.tracePath) {
        appendTrace(opts.tracePath, {
          type: "tool",
          server: opts.server,
          name,
          args,
          result,
          isError: hit.isError,
          ms: Date.now() - start,
        });
      }
      return result;
    },
    async close() {},
  };
}
