import type { IncomingMessage, ServerResponse } from "node:http";
import { resolve } from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import type { Request } from "../../packages/core/src/policy/reasoning/service.js";
import { NovaService } from "../../packages/core/src/policy/reasoning/service.js";

const service = new NovaService();
async function api(req: IncomingMessage, res: ServerResponse, next: () => void) {
  if (req.url?.split("?")[0] !== "/nova-api") return next();
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
      if (Buffer.byteLength(body) > 64_000) throw new Error("Request too large.");
    }
    const result = service.run(JSON.parse(body) as Request);
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
      },
      configurePreviewServer(server) {
        server.middlewares.use(api);
      },
    },
  ],
  server: {
    host: "127.0.0.1",
    port: 5180,
    strictPort: true,
    fs: { allow: [resolve(import.meta.dirname, "../..")] },
  },
  preview: { host: "127.0.0.1", port: 5180, strictPort: true },
  build: {
    outDir: "dist-nova",
    rollupOptions: { input: resolve(import.meta.dirname, "nova.html") },
  },
});
