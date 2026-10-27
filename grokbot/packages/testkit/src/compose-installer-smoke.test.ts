import { execFileSync } from "node:child_process";
import path from "node:path";
import { describe, expect, it } from "vitest";

const describeFast = process.env.VERIFY_PROVIDERS ? describe.skip : describe;
const repoRoot = path.resolve(import.meta.dirname, "../../../..");

describeFast("compose installer smoke scripts", () => {
  it("passes every grokbot/infra/compose/*.smoke.sh", () => {
    const runner = path.resolve(repoRoot, "grokbot/infra/compose/run-smokes.sh");
    const output = execFileSync("bash", [runner], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
      cwd: repoRoot,
    });
    expect(output).toMatch(/==>/);
  });
});
