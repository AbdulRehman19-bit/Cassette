import Anthropic from "@anthropic-ai/sdk";
import { connectGithub, runAgent } from "./agent.js";

/** Usage: node dist/main.js <owner/repo> <fromTag> <toTag>  (or env REPO, FROM_TAG, TO_TAG) */
async function main() {
  const [repo = process.env.REPO, fromTag = process.env.FROM_TAG, toTag = process.env.TO_TAG] = process.argv.slice(2);
  if (!repo || !fromTag || !toTag) {
    console.error("usage: changelogcat <owner/repo> <fromTag> <toTag>");
    process.exit(2);
  }
  const host = await connectGithub();
  try {
    const result = await runAgent({ repo, fromTag, toTag }, host, new Anthropic(), {
      model: process.env.MODEL ?? "claude-sonnet-5-5",
    });
    if (result.stoppedByLimit) console.error("warning: stopped at step limit");
    process.stdout.write(result.output + "\n");
  } finally {
    await host.close();
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
