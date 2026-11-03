import { readFileSync } from "node:fs";
import Logic from "logic-solver";

// Isolated optional research dependency. Parent bounds wall time, V8 heap and output size.
try {
  const { variables, clauses } = JSON.parse(readFileSync(0, "utf8"));
  const solver = new Logic.Solver();
  for (const clause of clauses)
    solver.require(Logic.or(clause.map((value) => `${value < 0 ? "-" : ""}v${Math.abs(value)}`)));
  const solution = solver.solve();
  process.stdout.write(
    JSON.stringify(
      solution
        ? {
            status: "sat",
            trueVariables: solution
              .getTrueVars()
              .filter((name) => /^v\d+$/.test(name))
              .map((name) => Number(name.slice(1)))
              .filter((n) => n <= variables),
          }
        : { status: "unsat" },
    ),
  );
} catch {
  process.stdout.write(
    JSON.stringify({ status: "unknown", reason: "SAT worker failed or dependency unavailable." }),
  );
}
