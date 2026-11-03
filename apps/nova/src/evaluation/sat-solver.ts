import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import type { SatResult, SatSolver } from "@rakazo/policy-runtime/bounded-equivalence";

/** MiniSat compiled to JS, run offline in a killable child rather than in the application process. */
export function miniSatSolver(timeoutMs = 10_000): SatSolver {
  if (!Number.isInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 60_000)
    throw new Error("SAT timeout must be between 1 and 60,000 milliseconds.");
  return (formula) => {
    const result = spawnSync(
      process.execPath,
      ["--max-old-space-size=256", fileURLToPath(new URL("./sat-worker.mjs", import.meta.url))],
      {
        input: JSON.stringify(formula),
        encoding: "utf8",
        timeout: timeoutMs,
        maxBuffer: 8 * 1024 * 1024,
      },
    );
    if (result.error || result.status !== 0)
      return {
        status: "unknown",
        reason:
          result.error && "code" in result.error && result.error.code === "ETIMEDOUT"
            ? "SAT solver timed out."
            : "SAT solver unavailable, exited or exceeded a resource limit.",
      };
    try {
      const value = JSON.parse(result.stdout) as SatResult;
      if (
        value.status === "unsat" ||
        (value.status === "sat" && Array.isArray(value.trueVariables))
      )
        return value;
    } catch {
      /* A malformed response cannot establish equivalence. */
    }
    return { status: "unknown", reason: "SAT solver did not return a supported result." };
  };
}
