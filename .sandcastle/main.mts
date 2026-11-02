import { run, cursor } from "@ai-hero/sandcastle";
import { docker } from "@ai-hero/sandcastle/sandboxes/docker";

await run({
  agent: cursor("grok-4.7-medium"),
  sandbox: docker({ imageName: "sandcastle:local" }),
  branchStrategy: { type: "head" },
  prompt:
    "Create PRACTICE.md with exactly this sentence: Sandcastle ran the Cursor agent in Docker. Commit that file. Then output <promise>COMPLETE</promise>.",
});
