// A tiny deterministic MCP server. Every tool call appends a line to LIVE_COUNT_FILE
// so tests can prove whether the "real" server was touched.
import { appendFileSync } from "node:fs";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";

const server = new Server({ name: "fake-github", version: "0.0.0" }, { capabilities: { tools: {} } });
const tools = [
  { name: "list_pull_requests", description: "list", inputSchema: { type: "object", properties: { state: { type: "string" } } } },
  { name: "get_pull_request", description: "get", inputSchema: { type: "object", properties: { number: { type: "number" } } } },
];
server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools }));
server.setRequestHandler(CallToolRequestSchema, async (req) => {
  if (process.env.LIVE_COUNT_FILE) appendFileSync(process.env.LIVE_COUNT_FILE, req.params.name + "\n");
  const text =
    req.params.name === "list_pull_requests"
      ? JSON.stringify([{ number: 7, title: "Add dark mode", merged_at: new Date().toISOString() }])
      : JSON.stringify({ number: req.params.arguments?.number, title: "Add dark mode", body: "Adds a dark theme." });
  return { content: [{ type: "text", text }] };
});
await server.connect(new StdioServerTransport());
