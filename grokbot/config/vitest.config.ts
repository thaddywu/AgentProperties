import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  root: fileURLToPath(new URL("../../", import.meta.url)),
  test: {
    environment: "node",
    setupFiles: ["./grokbot/packages/testkit/src/pin-test-env.ts"],
    include: [
      "apps/nova/tests/**/*.test.ts",
      "runtime/tests/**/*.test.ts",
      "translation/src/**/*.test.ts",
      ".agents/skills/pr-watch/*.test.ts",
      "grokbot/packages/*/src/**/*.test.{ts,tsx}",
      "grokbot/infra/sandboxes/supervisor/src/**/*.test.ts",
      "grokbot/infra/updater/src/**/*.test.ts",
      "grokbot/apps/desktop/src/**/*.test.ts",
      "grokbot/apps/web/src/**/*.test.{ts,tsx}",
      "grokbot/apps/mobile/lib/**/*.test.ts",
      "grokbot/apps/mobile/plugins/**/*.test.js",
      "grokbot/apps/api/src/**/*.test.ts",
      "grokbot/apps/www/src/**/*.test.ts",
    ],
    testTimeout: 30_000,
    hookTimeout: 60_000,
  },
});
