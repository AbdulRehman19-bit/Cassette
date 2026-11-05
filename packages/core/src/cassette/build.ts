import type { TraceEvent } from "../trace.js";
import type { Cassette, Step } from "./schema.js";
import { CASSETTE_VERSION } from "./schema.js";

export interface BuildMeta {
  scenario: string;
  input: Record<string, unknown>;
  output: string;
  agent?: Cassette["agent"];
  recordedAt?: string;
}

/** Fold a run's trace into a cassette: model/tool events become ordered steps; tool listings become toolSchemas. */
export function buildCassette(events: TraceEvent[], meta: BuildMeta): Cassette {
  const steps: Step[] = [];
  const toolSchemas: Cassette["toolSchemas"] = {};
  for (const ev of events) {
    if (ev.type === "model") {
      steps.push({ i: steps.length, type: "model", request: ev.request, response: ev.response, usage: ev.usage, ms: ev.ms });
    } else if (ev.type === "tool") {
      steps.push({
        i: steps.length,
        type: "tool",
        server: ev.server,
        name: ev.name,
        args: ev.args,
        result: ev.result,
        isError: ev.isError,
        ms: ev.ms,
      });
    } else if (ev.type === "tools") {
      toolSchemas[ev.server] = ev.tools; // latest listing wins
    }
  }
  return {
    version: CASSETTE_VERSION,
    scenario: meta.scenario,
    recordedAt: meta.recordedAt ?? new Date().toISOString(),
    agent: meta.agent ?? {},
    input: meta.input,
    steps,
    output: meta.output,
    toolSchemas,
  };
}
