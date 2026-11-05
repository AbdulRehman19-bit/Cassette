import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import type { Transport } from "@modelcontextprotocol/sdk/shared/transport.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import type { ToolBackend } from "./backend.js";

/**
 * Presents `backend` to the agent as an MCP server. The agent cannot tell it
 * from the real thing; the backend decides whether calls are forwarded
 * (record) or answered from a cassette (replay).
 */
export async function serveProxy(backend: ToolBackend, transport: Transport, name = "cassette-proxy"): Promise<Server> {
  const server = new Server({ name, version: "0.0.0" }, { capabilities: { tools: {} } });

  server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: (await backend.listTools()).map((t) => ({
      name: t.name,
      description: t.description,
      inputSchema: t.inputSchema as { type: "object" },
    })),
  }));

  server.setRequestHandler(CallToolRequestSchema, async (req) => {
    const args = (req.params.arguments ?? {}) as Record<string, unknown>;
    return (await backend.callTool(req.params.name, args)) as never;
  });

  server.onclose = () => {
    void backend.close();
  };
  await server.connect(transport);
  return server;
}
