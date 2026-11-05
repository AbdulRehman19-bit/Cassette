// A scripted "agent": two tool calls over MCP, then a final answer. The model is a
// deterministic fake so the e2e test needs no API key; it is wrapped by Cassette
// exactly like a real Anthropic client would be.
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { maybeWrapModel } from "../../dist/index.js";

const fakeModel = {
  messages: {
    async create(params) {
      const turn = params.messages.filter((m) => m.role === "assistant").length;
      const usage = { input_tokens: 10 + turn, output_tokens: 5 };
      if (turn === 0) return { id: "msg_aaaaaaaa1", content: [{ type: "tool_use", id: "toolu_aaaaaaaa1", name: "list_pull_requests", input: { state: "closed" } }], usage };
      if (turn === 1) return { id: "msg_aaaaaaaa2", content: [{ type: "tool_use", id: "toolu_aaaaaaaa2", name: "get_pull_request", input: { number: 7 } }], usage };
      return { id: "msg_aaaaaaaa3", content: [{ type: "text", text: "## New\n- Dark mode" }], usage };
    },
  },
};
const model = maybeWrapModel(fakeModel);

const transport = new StdioClientTransport({
  command: process.env.MCP_FAKE_COMMAND,
  args: JSON.parse(process.env.MCP_FAKE_ARGS),
});
const client = new Client({ name: "fake-agent", version: "0" });
await client.connect(transport);
await client.listTools();

const messages = [{ role: "user", content: "go" }];
for (;;) {
  const res = await model.messages.create({ messages });
  messages.push({ role: "assistant", content: res.content });
  const use = res.content.find((b) => b.type === "tool_use");
  if (!use) {
    process.stdout.write(res.content.map((b) => b.text).join("") + "\n");
    break;
  }
  const out = await client.callTool({ name: use.name, arguments: use.input });
  messages.push({ role: "user", content: [{ type: "tool_result", tool_use_id: use.id, content: out.content[0].text }] });
}
await client.close();
