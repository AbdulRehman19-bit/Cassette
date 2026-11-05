import { appendTrace } from "../trace.js";
import type { Cassette, ModelStep } from "../cassette/schema.js";
import type { MessagesClient } from "./wrap.js";

/** Env var pointing at a cassette whose model responses should be served instead of calling the API. */
export const REPLAY_MODEL_ENV = "CASSETTE_REPLAY_MODEL";

/**
 * Serves recorded model responses in order. Used by `--offline` so a full run
 * costs nothing and is fully deterministic. Requests are logged to the trace
 * like a live call; a run that asks for more model turns than were recorded
 * fails loudly rather than inventing an answer.
 */
export function replayModel(cassette: Cassette, opts: { tracePath?: string } = {}): MessagesClient {
  const steps = cassette.steps.filter((s): s is ModelStep => s.type === "model");
  let next = 0;
  return {
    messages: {
      create: async (params: unknown) => {
        const step = steps[next++];
        if (!step) throw new Error(`cassette: no recorded model response for turn ${next} (recorded ${steps.length})`);
        if (opts.tracePath) {
          appendTrace(opts.tracePath, { type: "model", request: params, response: step.response, usage: step.usage, ms: step.ms });
        }
        return step.response;
      },
    },
  };
}
