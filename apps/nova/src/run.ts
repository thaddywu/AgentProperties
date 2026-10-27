import { createEpisode } from "./runtime.js";

// Standalone application entry point, using the same real transitions as the UI preset.
const runtime = createEpisode("denial");
const pending = runtime.state.messages.find((message) => message.status === "pending");
if (!pending) throw new Error("The Nova denial scenario must have a pending message.");
const decision = runtime.settle(pending.id);
console.log(
  JSON.stringify(
    {
      scenario: "third-part-denied",
      allowed: decision.allowed,
      message: pending.id,
      recipient: pending.to,
      events: runtime.state.events.length,
    },
    null,
    2,
  ),
);
if (decision.allowed) process.exitCode = 1;
