import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeAll, describe, expect, it } from "vitest";
import { parseConfig, runScenario, readScenario } from "../src/index.js";

const here = dirname(fileURLToPath(import.meta.url));
const cliPath = resolve(here, "../../cli/dist/index.js");
const fixtures = join(here, "fixtures");

let dir: string;
let counter: string;
let cfgPath: string;

const liveCalls = () => (existsSync(counter) ? readFileSync(counter, "utf8").split("\n").filter(Boolean).length : 0);
const cfg = () => parseConfig(readFileSync(cfgPath, "utf8"), cfgPath);

beforeAll(async () => {
  expect(existsSync(cliPath), "run `pnpm build` before the e2e test").toBe(true);
  dir = await mkdtemp(join(tmpdir(), "cassette-e2e-"));
  counter = join(dir, "live-calls.txt");
  cfgPath = join(dir, "cassette.yaml");
  const q = (p: string) => JSON.stringify(p);
  writeFileSync(
    cfgPath,
    [
      "agent:",
      `  command: ${q(`node ${join(fixtures, "fake-agent.mjs")}`)}`,
      "servers:",
      "  fake:",
      "    command: node",
      `    args: [${q(join(fixtures, "fake-server.mjs"))}]`,
      `    env: { LIVE_COUNT_FILE: ${q(counter)} }`,
      "scenarios:",
      "  - name: basic",
      "    input: { repo: acme/widgets }",
    ].join("\n"),
  );
}, 30_000);

describe("record → replay", () => {
  it("records a run into a cassette", async () => {
    const run = await runScenario(cfg(), "basic", { mode: "record", cliPath, quiet: true });
    expect(run.exitCode).toBe(0);
    expect(run.written).toBeDefined();
    const c = await readScenario(cfg().cassettesPath, "basic");
    expect(c.steps.map((s) => s.type)).toEqual(["model", "tool", "model", "tool", "model"]);
    expect(c.output).toBe("## New\n- Dark mode");
    expect(Object.keys(c.toolSchemas)).toEqual(["fake"]);
    expect(liveCalls()).toBe(2);
  }, 30_000);

  it("replays with zero live tool calls and the same output", async () => {
    const before = liveCalls();
    const run = await runScenario(cfg(), "basic", { mode: "replay", cliPath, quiet: true });
    expect(run.exitCode).toBe(0);
    expect(run.divergences).toEqual([]);
    expect(run.cassette.output).toBe("## New\n- Dark mode");
    expect(liveCalls()).toBe(before);
  }, 30_000);

  it("replays twice to the same result", async () => {
    const a = await runScenario(cfg(), "basic", { mode: "replay", cliPath, quiet: true });
    const b = await runScenario(cfg(), "basic", { mode: "replay", cliPath, quiet: true });
    const tools = (r: typeof a) => r.cassette.steps.flatMap((s) => (s.type === "tool" ? [[s.name, s.args, s.result]] : []));
    expect(tools(a)).toEqual(tools(b));
  }, 60_000);

  it("`cassette test --offline` exits 0 and reports identical output", () => {
    const before = liveCalls();
    const out = execFileSync(process.execPath, [cliPath, "test", "--offline", "-c", cfgPath], { encoding: "utf8" });
    expect(out).toContain("output identical");
    expect(liveCalls()).toBe(before);
  }, 30_000);

  it("reports divergence (and exits 1) when the agent makes a call that was never recorded", async () => {
    // Re-record, then corrupt the cassette so the agent's get_pull_request(7) has no answer.
    const path = join(cfg().cassettesPath, "basic.cassette.json");
    const c = JSON.parse(readFileSync(path, "utf8")) as { steps: { type: string; name?: string }[] };
    c.steps = c.steps.filter((s) => s.name !== "get_pull_request");
    writeFileSync(path, JSON.stringify(c));
    let status = 0;
    try {
      execFileSync(process.execPath, [cliPath, "test", "-c", cfgPath], { encoding: "utf8", stdio: "pipe" });
    } catch (e) {
      status = (e as { status: number }).status;
    }
    expect(status).toBe(1);
  }, 30_000);
});
