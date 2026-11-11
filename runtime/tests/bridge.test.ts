import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createInterface } from "node:readline";
import { PassThrough } from "node:stream";
import { fileURLToPath } from "node:url";
import { expect, it } from "vitest";
import { compileApplicationPolicy } from "../src/application.js";
import { servePolicyBridge } from "../src/bridge.js";
import { binding, policy } from "./fixtures/action-contract.js";

it.each(["typescript", "python", "python-worker"])(
  "runs the same Python backend conformance against %s",
  (engine) => {
    const directory = mkdtempSync(join(tmpdir(), "policy-bridge-"));
    try {
      const config = join(directory, "contract.json");
      writeFileSync(
        config,
        JSON.stringify({ binding, bundle: compileApplicationPolicy(binding, policy) }),
      );
      const command =
        engine === "python"
          ? ["native"]
          : engine === "python-worker"
            ? ["python3", "-m", "policy_runtime", "serve"]
            : [
                process.execPath,
                "--import",
                new URL("../../grokbot/node_modules/tsx/dist/loader.mjs", import.meta.url).href,
                fileURLToPath(new URL("../src/bridge-cli.ts", import.meta.url)),
              ];
      const result = spawnSync(
        "python3",
        [
          fileURLToPath(new URL("../python/tests/conformance.py", import.meta.url)),
          config,
          JSON.stringify(command),
        ],
        {
          encoding: "utf8",
          timeout: 25_000,
          maxBuffer: 100_000,
          env: {
            ...process.env,
            PYTHONPATH: fileURLToPath(new URL("../python/", import.meta.url)),
          },
        },
      );
      expect(result.error).toBeUndefined();
      expect(result.status, `${result.stdout}\n${result.stderr}`).toBe(0);
      expect(result.stderr).toContain("OK");
    } finally {
      rmSync(directory, { recursive: true, force: true });
    }
  },
  30_000,
);

it("requests cleanup when transaction begin times out instead of abandoning the backend boundary", async () => {
  const input = new PassThrough();
  const output = new PassThrough();
  const lines = createInterface({ input: output });
  const callbacks: string[] = [];
  const replies = new Map<string, (message: { ok: boolean }) => void>();
  lines.on("line", (line) => {
    const message = JSON.parse(line);
    if (message.type === "callback") {
      callbacks.push(message.kind);
      if (message.kind === "rollback")
        input.write(
          `${JSON.stringify({ type: "callback_result", id: message.id, ok: true, value: { notApplied: false } })}\n`,
        );
    } else replies.get(message.id)?.(message);
  });
  const server = servePolicyBridge(input, output, 10);
  const request = (id: string, method: string, params: unknown) =>
    new Promise<{ ok: boolean }>((resolve) => {
      replies.set(id, resolve);
      input.write(`${JSON.stringify({ type: "request", id, method, params })}\n`);
    });
  try {
    expect(
      (
        await request("configure", "configure", {
          binding,
          bundle: compileApplicationPolicy(binding, policy),
          observations: [],
          operations: [{ action: "apply" }],
        })
      ).ok,
    ).toBe(true);
    expect(
      (
        await request("execute", "execute", {
          actor: "operator",
          action: "apply",
          resource: "item",
          parameters: { version: "v1" },
        })
      ).ok,
    ).toBe(false);
    expect(callbacks).toEqual(["begin", "rollback"]);
  } finally {
    input.end();
    await server;
    lines.close();
    output.end();
  }
});
