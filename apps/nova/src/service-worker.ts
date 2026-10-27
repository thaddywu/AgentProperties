import type { RuntimeState } from "./runtime.js";
import { NovaRuntime } from "./runtime.js";
import type { Request } from "./service.js";
import { NovaService } from "./service.js";

const service = new NovaService();
process.on(
  "message",
  (message: { request?: Request; checkpoint?: { state: RuntimeState; version: number } }) => {
    if (message.checkpoint) {
      service.runtime = new NovaRuntime(message.checkpoint.state);
      service.version = message.checkpoint.version;
    }
    const before = { state: service.runtime.snapshot(), version: service.version };
    try {
      const result = message.request ? service.run(message.request) : service.state();
      process.send?.({
        result,
        checkpoint: { state: service.runtime.snapshot(), version: service.version },
      });
    } catch (error) {
      service.runtime = new NovaRuntime(before.state);
      service.version = before.version;
      process.send?.({ error: error instanceof Error ? error.message : "Evaluation failed" });
    }
  },
);
