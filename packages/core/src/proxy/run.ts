import { readFile } from "node:fs/promises";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { Cassette } from "../cassette/schema.js";
import { replayBackend } from "../replay/backend.js";
import { connectLive, type StdioServerSpec, type ToolBackend } from "./backend.js";
import { recording } from "./record.js";
import { serveProxy } from "./server.js";

export interface ProxyRunOptions {
  server: string;
  mode: "record" | "replay";
  tracePath: string;
  /** replay: cassette to answer from. */
  cassettePath?: string;
  /** record: the real server to spawn. */
  command?: string;
  /** record: JSON file {command,args,env} describing the real server; keeps secrets off argv. */
  specPath?: string;
  args?: string[];
  ignoreArgs?: string[];
  tolerance?: "exact" | "normalized";
}

/**
 * Process entrypoint for `cassette proxy`: the agent spawns this as if it were
 * the MCP server, over stdio. In replay mode the real server is never spawned.
 */
export async function runProxy(opts: ProxyRunOptions): Promise<void> {
  let backend: ToolBackend;
  if (opts.mode === "replay") {
    if (!opts.cassettePath) throw new Error("replay mode needs a cassette path");
    const cassette = Cassette.parse(JSON.parse(await readFile(opts.cassettePath, "utf8")));
    backend = replayBackend(cassette, {
      server: opts.server,
      tracePath: opts.tracePath,
      ignoreArgs: opts.ignoreArgs,
      tolerance: opts.tolerance,
    });
  } else {
    const spec = opts.specPath
      ? (JSON.parse(await readFile(opts.specPath, "utf8")) as StdioServerSpec)
      : opts.command
        ? { command: opts.command, args: opts.args }
        : undefined;
    if (!spec) throw new Error("record mode needs the real server (--spec or a command)");
    backend = recording(await connectLive(spec), {
      server: opts.server,
      tracePath: opts.tracePath,
    });
  }
  await serveProxy(backend, new StdioServerTransport());
}
