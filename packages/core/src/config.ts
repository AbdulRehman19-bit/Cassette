import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { parse } from "yaml";
import { z } from "zod";

export const ServerConfig = z.object({
  transport: z.enum(["stdio"]).default("stdio"),
  command: z.string(),
  args: z.array(z.string()).optional(),
  env: z.record(z.string(), z.string()).optional(),
});

export const Scenario = z.object({
  name: z.string().regex(/^[\w.-]+$/, "scenario names may only contain letters, digits, _ . -"),
  input: z.record(z.string(), z.unknown()).default({}),
});

export const DiffConfig = z.object({
  ignoreArgs: z.array(z.string()).default([]),
  failOn: z.array(z.string()).default(["tool_added", "tool_removed", "tool_args_changed"]),
  tolerance: z.enum(["exact", "normalized"]).default("normalized"),
});

export const ConfigSchema = z.object({
  agent: z.object({
    command: z.string(),
    env: z.record(z.string(), z.string()).optional(),
  }),
  servers: z.record(z.string(), ServerConfig),
  scenarios: z.array(Scenario).min(1),
  cassettesDir: z.string().default("cassettes"),
  diff: DiffConfig.default({ ignoreArgs: [], failOn: ["tool_added", "tool_removed", "tool_args_changed"], tolerance: "normalized" }),
  assertions: z.array(z.record(z.string(), z.unknown())).default([]),
});

export type Config = z.infer<typeof ConfigSchema>;
export type ServerConfig = z.infer<typeof ServerConfig>;

export interface LoadedConfig extends Config {
  /** Directory of the config file; relative paths resolve against it. */
  root: string;
  /** Absolute cassettes dir. */
  cassettesPath: string;
}

/** Split `"npx -y pkg"` into command + args when no explicit args are given. */
export function splitCommand(server: ServerConfig): { command: string; args: string[] } {
  if (server.args) return { command: server.command, args: server.args };
  const [cmd = "", ...args] = server.command.trim().split(/\s+/);
  return { command: cmd, args };
}

export function parseConfig(text: string, configPath: string): LoadedConfig {
  const raw: unknown = parse(text);
  const cfg = ConfigSchema.parse(raw);
  const root = dirname(resolve(configPath));
  return { ...cfg, root, cassettesPath: resolve(root, cfg.cassettesDir) };
}

export async function loadConfig(path: string): Promise<LoadedConfig> {
  return parseConfig(await readFile(path, "utf8"), path);
}

