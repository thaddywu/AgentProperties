import { readFileSync } from "node:fs";
import type { IncomingMessage, ServerResponse } from "node:http";
import { resolve } from "node:path";
import type { Request } from "@rakazo/nova/service";
import { ServiceProcess } from "@rakazo/nova/service-process";
import { NOVA_WORKER_PATH } from "@rakazo/nova/worker-path";
import { QUESTION_INSTRUCTIONS } from "@rakazo/policy-translation/question";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { tsImport } from "tsx/esm/api";
import { defineConfig } from "vite";
import type { questionHandler as QuestionHandler } from "./src/features/nova/server-question.ts";

const service = new ServiceProcess(NOVA_WORKER_PATH, process.env.NOVA_STATE_FILE);
process.once("exit", () => service.close());
const { questionHandler }: { questionHandler: typeof QuestionHandler } = await tsImport(
  "./src/features/nova/server-question.ts",
  import.meta.url,
);
const connection = process.env.MODEL_CONNECTION_FILE
  ? JSON.parse(readFileSync(process.env.MODEL_CONNECTION_FILE, "utf8"))
  : undefined;
const interpret = questionHandler(
  service,
  connection
    ? async (prompt) => {
        // The optional provider stack ships TS workspace sources; load it only for model questions.
        const { connectionGenerator } = await tsImport(
          "@rakazo/policy-translation/model",
          import.meta.url,
        );
        return connectionGenerator(connection, QUESTION_INSTRUCTIONS, 60_000)(prompt);
      }
    : undefined,
);
async function api(req: IncomingMessage, res: ServerResponse, next: () => void) {
  const pathname = req.url?.split("?")[0];
  if (
    (req.method === "GET" || req.method === "HEAD") &&
    (pathname === "/" || pathname === "/index.html")
  ) {
    const query = req.url?.includes("?") ? req.url.slice(req.url.indexOf("?")) : "";
    res.writeHead(302, { Location: `/nova.html${query}`, "Cache-Control": "no-store" });
    res.end();
    return;
  }
  if (pathname !== "/nova-api" && pathname !== "/nova-question") return next();
  res.setHeader("Content-Type", "application/json");
  res.setHeader("Cache-Control", "no-store");
  try {
    if (req.method !== "POST" || !req.headers["content-type"]?.startsWith("application/json"))
      throw new Error("Use POST with application/json.");
    const origin = req.headers.origin;
    if (origin && new URL(origin).host !== req.headers.host)
      throw new Error("Cross-origin requests are not accepted.");
    let body = "";
    for await (const chunk of req) {
      body += chunk;
      if (Buffer.byteLength(body) > 256_000) throw new Error("Request too large.");
    }
    const result =
      pathname === "/nova-question"
        ? await interpret(JSON.parse(body))
        : await service.run(JSON.parse(body) as Request);
    res.end(JSON.stringify({ result }));
  } catch (error) {
    res.statusCode = 400;
    res.end(JSON.stringify({ error: error instanceof Error ? error.message : "Request failed" }));
  }
}
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    {
      name: "nova-local-runtime",
      configureServer(server) {
        server.middlewares.use(api);
        server.httpServer?.once("close", () => service.close());
      },
      configurePreviewServer(server) {
        server.middlewares.use(api);
        server.httpServer?.once("close", () => service.close());
      },
    },
  ],
  server: {
    host: "127.0.0.1",
    port: 5180,
    strictPort: true,
    fs: { allow: [resolve(import.meta.dirname, "../../..")] },
  },
  preview: { host: "127.0.0.1", port: 5180, strictPort: true },
  build: {
    outDir: "dist-nova",
    rollupOptions: { input: resolve(import.meta.dirname, "nova.html") },
  },
});
