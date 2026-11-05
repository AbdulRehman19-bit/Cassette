import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

export interface ToolInfo {
  name: string;
  description?: string;
  inputSchema: Record<string, unknown>;
}

export interface CallResult {
  content: unknown[];
  isError?: boolean;
  [k: string]: unknown;
}

/** What the proxy forwards to. Live = the real MCP server; replay = a cassette. */
export interface ToolBackend {
  listTools(): Promise<ToolInfo[]>;
  callTool(name: string, args: Record<string, unknown>): Promise<CallResult>;
  close(): Promise<void>;
}

export interface StdioServerSpec {
  command: string;
  args?: string[];
  env?: Record<string, string>;
}

/** Spawns the real MCP server over stdio and talks to it as a client. */
export async function connectLive(spec: StdioServerSpec): Promise<ToolBackend> {
  const transport = new StdioClientTransport({
    command: spec.command,
    args: spec.args ?? [],
    env: { ...(process.env as Record<string, string>), ...spec.env },
  });
  const client = new Client({ name: "cassette-proxy", version: "0.0.0" });
  await client.connect(transport);
  return {
    async listTools() {
      const { tools } = await client.listTools();
      return tools.map((t) => ({
        name: t.name,
        description: t.description,
        inputSchema: t.inputSchema as Record<string, unknown>,
      }));
    },
    async callTool(name, args) {
      return (await client.callTool({ name, arguments: args })) as CallResult;
    },
    close: () => client.close(),
  };
}
