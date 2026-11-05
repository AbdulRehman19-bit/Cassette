import { appendFileSync, existsSync, readFileSync } from "node:fs";

/**
 * A trace is an append-only JSONL file shared by every Cassette component that
 * observes a run (the MCP proxy process and the model wrapper in the agent
 * process). The runner folds it into a cassette once the run ends. Append order
 * is the step order.
 */
export type TraceEvent =
  | { type: "model"; request: unknown; response: unknown; usage?: { in: number; out: number }; ms?: number }
  | {
      type: "tool";
      server: string;
      name: string;
      args: Record<string, unknown>;
      result: unknown;
      isError?: boolean;
      ms?: number;
    }
  | { type: "tools"; server: string; tools: { name: string; inputSchema: unknown }[] }
  | { type: "divergence"; server: string; name: string; args: Record<string, unknown>; reason: string };

export function appendTrace(path: string, event: TraceEvent): void {
  // Sync append of one line keeps events from concurrent processes whole and ordered.
  appendFileSync(path, JSON.stringify(event) + "\n", "utf8");
}

export function readTrace(path: string): TraceEvent[] {
  if (!existsSync(path)) return [];
  return readFileSync(path, "utf8")
    .split("\n")
    .filter((l) => l.trim())
    .map((l) => JSON.parse(l) as TraceEvent);
}
