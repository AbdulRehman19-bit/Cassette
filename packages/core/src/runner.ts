import { spawn } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { buildCassette } from "./cassette/build.js";
import type { Cassette } from "./cassette/schema.js";
import { cassettePath, readScenario, writeCassette } from "./cassette/store.js";
import { splitCommand, type LoadedConfig } from "./config.js";
import { REPLAY_MODEL_ENV } from "./model/replay.js";
import { TRACE_ENV } from "./model/wrap.js";
import { readTrace } from "./trace.js";

export interface RunOptions {
  mode: "record" | "replay";
  /** Replay the recorded model too (zero API cost). */
  offline?: boolean;
  /** Override the agent's model via the MODEL env var. */
  model?: string;
  /** Path to the cassette CLI entry the agent should spawn as its MCP "server". */
  cliPath: string;
  /** Don't print the agent's stderr. */
  quiet?: boolean;
}

export interface ScenarioRun {
  scenario: string;
  cassette: Cassette;
  exitCode: number;
  stderr: string;
  /** Live calls that had no recorded answer (replay only). */
  divergences: { server: string; name: string; args: Record<string, unknown>; reason: string }[];
  /** Cassette file written (record only). */
  written?: string;
}

const upperSnake = (k: string) => k.replace(/([a-z0-9])([A-Z])/g, "$1_$2").replace(/[^A-Za-z0-9]+/g, "_").toUpperCase();

/** Env var names an agent reads to find each MCP server: MCP_<SERVER>_COMMAND and MCP_<SERVER>_ARGS (JSON array). */
export const serverEnvNames = (server: string) => ({
  command: `MCP_${upperSnake(server)}_COMMAND`,
  args: `MCP_${upperSnake(server)}_ARGS`,
});

export async function runScenario(cfg: LoadedConfig, scenarioName: string, opts: RunOptions): Promise<ScenarioRun> {
  const scenario = cfg.scenarios.find((s) => s.name === scenarioName);
  if (!scenario) throw new Error(`unknown scenario: ${scenarioName}`);

  const baseline = opts.mode === "replay" ? await readScenario(cfg.cassettesPath, scenarioName) : undefined;
  const dir = await mkdtemp(join(tmpdir(), "cassette-run-"));
  const tracePath = join(dir, "trace.jsonl");
  try {
    const env: Record<string, string> = { ...(process.env as Record<string, string>), ...cfg.agent.env };
    env[TRACE_ENV] = tracePath;
    if (opts.model) env.MODEL = opts.model;
    env.CASSETTE_INPUT = JSON.stringify(scenario.input);
    for (const [k, v] of Object.entries(scenario.input)) if (typeof v === "string") env[upperSnake(k)] = v;
    if (opts.offline) {
      if (!baseline) throw new Error("--offline needs replay mode");
      env[REPLAY_MODEL_ENV] = cassettePath(cfg.cassettesPath, scenarioName);
    }

    for (const [name, server] of Object.entries(cfg.servers)) {
      const real = splitCommand(server);
      const args = [opts.cliPath, "proxy", "--server", name, "--mode", opts.mode, "--trace", tracePath];
      if (baseline) args.push("--cassette", cassettePath(cfg.cassettesPath, scenarioName));
      if (cfg.diff.ignoreArgs.length) args.push("--ignore-args", cfg.diff.ignoreArgs.join(","));
      args.push("--tolerance", cfg.diff.tolerance);
      if (opts.mode === "record") {
        // The real server's command and env go through a private temp file, not argv, so secrets stay off the process list.
        const specPath = join(dir, `server-${name}.json`);
        const serverEnv = Object.fromEntries(Object.entries(server.env ?? {}).map(([k, v]) => [k, expandEnv(v)]));
        await writeFile(specPath, JSON.stringify({ command: real.command, args: real.args, env: serverEnv }), { mode: 0o600 });
        args.push("--spec", specPath);
      }
      const names = serverEnvNames(name);
      env[names.command] = process.execPath;
      env[names.args] = JSON.stringify(args);
    }

    const { code, stdout, stderr } = await exec(cfg.agent.command, cfg.root, env, opts.quiet);
    const events = readTrace(tracePath);
    const agentModel = env.MODEL;
    const cassette = buildCassette(events, {
      scenario: scenarioName,
      input: scenario.input,
      output: stdout.trim(),
      agent: agentModel ? { model: agentModel } : {},
    });
    const divergences = events.flatMap((e) =>
      e.type === "divergence" ? [{ server: e.server, name: e.name, args: e.args, reason: e.reason }] : [],
    );
    const run: ScenarioRun = { scenario: scenarioName, cassette, exitCode: code, stderr, divergences };
    if (opts.mode === "record" && code === 0) run.written = await writeCassette(cfg.cassettesPath, cassette);
    return run;
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

function exec(command: string, cwd: string, env: Record<string, string>, quiet?: boolean) {
  return new Promise<{ code: number; stdout: string; stderr: string }>((resolve, reject) => {
    const child = spawn(command, { cwd, env, shell: true, stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d: Buffer) => (stdout += d.toString()));
    child.stderr.on("data", (d: Buffer) => {
      stderr += d.toString();
      if (!quiet) process.stderr.write(d);
    });
    child.on("error", reject);
    child.on("close", (code) => resolve({ code: code ?? 1, stdout, stderr }));
  });
}

/** Expand `${NAME}` from the runner's environment so configs can reference secrets without containing them. */
export function expandEnv(value: string, env: NodeJS.ProcessEnv = process.env): string {
  return value.replace(/\$\{(\w+)\}/g, (_m, name: string) => env[name] ?? "");
}
