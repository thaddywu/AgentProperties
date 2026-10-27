import { fileURLToPath } from "node:url";

export const NOVA_WORKER_PATH = fileURLToPath(new URL("./service-worker.ts", import.meta.url));
