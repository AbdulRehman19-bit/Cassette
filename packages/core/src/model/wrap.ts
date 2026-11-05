import { readFileSync } from "node:fs";
import { Cassette } from "../cassette/schema.js";
import { appendTrace } from "../trace.js";
import { REPLAY_MODEL_ENV, replayModel } from "./replay.js";

/** Structural shape of an Anthropic-style client; keeps core free of provider SDK deps. */
export interface MessagesClient {
  messages: { create(params: any): Promise<any> }; // eslint-disable-line @typescript-eslint/no-explicit-any
}

interface Usage {
  input_tokens?: number;
  output_tokens?: number;
}

/**
 * Wraps a model client so each `messages.create` call appends request,
 * response, token usage and latency to the trace. The agent keeps using the
 * wrapped client exactly like the original.
 */
export function wrapModel<C extends MessagesClient>(client: C, opts: { tracePath: string }): C {
  const wrapped = Object.create(client) as C;
  wrapped.messages = {
    ...client.messages,
    create: async (params: unknown) => {
      const start = Date.now();
      const response = await client.messages.create(params);
      const usage = (response?.usage ?? undefined) as Usage | undefined;
      appendTrace(opts.tracePath, {
        type: "model",
        request: params,
        response,
        usage: usage ? { in: usage.input_tokens ?? 0, out: usage.output_tokens ?? 0 } : undefined,
        ms: Date.now() - start,
      });
      return response;
    },
  };
  return wrapped;
}

/** Env var the runner sets so an agent can opt in to recording without code changes. */
export const TRACE_ENV = "CASSETTE_TRACE";

/**
 * The one line an agent adds: `const client = maybeWrapModel(new Anthropic())`.
 * Under `cassette record|test` it logs calls; with `--offline` it serves the
 * recorded responses instead; outside Cassette it returns the client untouched.
 */
export function maybeWrapModel<C extends MessagesClient>(client: C, env = process.env): C {
  const tracePath = env[TRACE_ENV];
  const replayFrom = env[REPLAY_MODEL_ENV];
  if (replayFrom) {
    const cassette = Cassette.parse(JSON.parse(readFileSync(replayFrom, "utf8")));
    return replayModel(cassette, { tracePath }) as C;
  }
  return tracePath ? wrapModel(client, { tracePath }) : client;
}
