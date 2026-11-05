#!/usr/bin/env node
import { fileURLToPath } from "node:url";
import { Command } from "commander";
import pc from "picocolors";
import { loadConfig, runProxy, runScenario, readScenario, type LoadedConfig, type ScenarioRun } from "@cassette/core";

const cliPath = fileURLToPath(import.meta.url);

const program = new Command().name("cassette").description("pytest for agents: record, replay, diff and assert agent runs");

const pick = (cfg: LoadedConfig, filter?: string) => {
  const names = cfg.scenarios.map((s) => s.name);
  if (!filter) return names;
  const re = new RegExp("^" + filter.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*") + "$");
  const hit = names.filter((n) => re.test(n));
  if (!hit.length) throw new Error(`no scenario matches "${filter}" (have: ${names.join(", ")})`);
  return hit;
};

program
  .command("record [scenario]")
  .description("run live (model + tools) and write cassettes")
  .option("-c, --config <file>", "config file", "cassette.yaml")
  .option("--model <id>", "override the agent's model")
  .action(async (scenario: string | undefined, o: { config: string; model?: string }) => {
    const cfg = await loadConfig(o.config);
    let failed = 0;
    for (const name of pick(cfg, scenario)) {
      const run = await runScenario(cfg, name, { mode: "record", model: o.model, cliPath });
      if (run.exitCode !== 0) {
        failed++;
        console.log(`${pc.red("×")} ${name}  agent exited with code ${run.exitCode}`);
      } else {
        const steps = run.cassette.steps.length;
        console.log(`${pc.green("●")} ${name}  recorded ${steps} steps → ${run.written}`);
      }
    }
    process.exitCode = failed ? 1 : 0;
  });

program
  .command("test [scenario]")
  .description("replay scenarios against their cassettes")
  .option("-c, --config <file>", "config file", "cassette.yaml")
  .option("--offline", "also replay the recorded model (no API calls)")
  .option("--model <id>", "try a different model")
  .option("--filter <glob>", "only scenarios matching the glob")
  .action(async (scenario: string | undefined, o: { config: string; offline?: boolean; model?: string; filter?: string }) => {
    const cfg = await loadConfig(o.config);
    let failed = 0;
    for (const name of pick(cfg, scenario ?? o.filter)) {
      const base = await readScenario(cfg.cassettesPath, name);
      const run: ScenarioRun = await runScenario(cfg, name, { mode: "replay", offline: o.offline, model: o.model, cliPath });
      const sameOutput = run.cassette.output === base.output;
      const ok = run.exitCode === 0 && run.divergences.length === 0 && (!o.offline || sameOutput);
      if (!ok) failed++;
      const toolCalls = run.cassette.steps.filter((s) => s.type === "tool").length;
      console.log(`${ok ? pc.green("✓") : pc.red("×")} ${name}  ${toolCalls} tool calls replayed, ${run.divergences.length} divergences${o.offline ? (sameOutput ? ", output identical" : ", output differs") : ""}`);
      for (const d of run.divergences) console.log(`    ${pc.red("!")} ${d.reason}`);
      if (run.exitCode !== 0) console.log(`    agent exited with code ${run.exitCode}`);
    }
    console.log(failed ? pc.red(`${failed} failed`) : pc.green("all passed"));
    process.exitCode = failed ? 1 : 0;
  });

// Internal: the agent spawns this as its MCP server.
program
  .command("proxy", { hidden: true })
  .requiredOption("--server <name>")
  .requiredOption("--mode <mode>")
  .requiredOption("--trace <file>")
  .option("--cassette <file>")
  .option("--spec <file>")
  .option("--ignore-args <list>")
  .option("--tolerance <t>")
  .argument("[command...]")
  .action(async (command: string[], o: { server: string; mode: "record" | "replay"; trace: string; cassette?: string; spec?: string; ignoreArgs?: string; tolerance?: "exact" | "normalized" }) => {
    await runProxy({
      server: o.server,
      mode: o.mode,
      tracePath: o.trace,
      cassettePath: o.cassette,
      specPath: o.spec,
      command: command[0],
      args: command.slice(1),
      ignoreArgs: o.ignoreArgs ? o.ignoreArgs.split(",") : undefined,
      tolerance: o.tolerance,
    });
  });

program.parseAsync().catch((e: unknown) => {
  console.error(pc.red(e instanceof Error ? e.message : String(e)));
  process.exit(2);
});
