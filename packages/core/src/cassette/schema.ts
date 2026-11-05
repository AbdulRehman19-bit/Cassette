import { z } from "zod";

export const CASSETTE_VERSION = 1;

const json: z.ZodType<unknown> = z.unknown();

export const ModelStep = z.object({
  i: z.number().int().nonnegative(),
  type: z.literal("model"),
  request: json,
  response: json,
  usage: z.object({ in: z.number(), out: z.number() }).optional(),
  ms: z.number().optional(),
});

export const ToolStep = z.object({
  i: z.number().int().nonnegative(),
  type: z.literal("tool"),
  server: z.string(),
  name: z.string(),
  args: z.record(z.string(), z.unknown()),
  result: json,
  isError: z.boolean().optional(),
  ms: z.number().optional(),
});

export const Step = z.discriminatedUnion("type", [ModelStep, ToolStep]);

export const ToolSchema = z.object({
  name: z.string(),
  inputSchema: z.unknown(),
});

export const Cassette = z.object({
  version: z.literal(CASSETTE_VERSION),
  scenario: z.string(),
  recordedAt: z.string(),
  agent: z.object({ model: z.string().optional(), promptHash: z.string().optional() }),
  input: z.record(z.string(), z.unknown()),
  steps: z.array(Step),
  output: z.string(),
  toolSchemas: z.record(z.string(), z.array(ToolSchema)),
});

export type ModelStep = z.infer<typeof ModelStep>;
export type ToolStep = z.infer<typeof ToolStep>;
export type Step = z.infer<typeof Step>;
export type Cassette = z.infer<typeof Cassette>;
