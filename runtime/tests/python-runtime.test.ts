import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, it } from "vitest";
import { compileApplicationPolicy, createPolicySession } from "../src/application.js";
import type { RuntimeBinding } from "../src/binding.js";
import { CAPABILITY_PREDICATES, PROVENANCE_PREDICATES } from "../src/foundations.js";
import { LIFECYCLE_PREDICATES } from "../src/lifecycle.js";
import { binding, policy } from "./fixtures/action-contract.js";

const f = (predicate: string, ...args: string[]) => ({ predicate, args });

it("runs standalone native Python security conformance without a TS subprocess", () => {
  const result = spawnSync(
    "python3",
    [
      "-m",
      "unittest",
      "discover",
      "-s",
      fileURLToPath(new URL("../python/tests/", import.meta.url)),
      "-p",
      "test_*.py",
    ],
    { encoding: "utf8", timeout: 25_000 },
  );
  expect(result.status, result.stderr).toBe(0);
  expect(result.stderr).toContain("OK");
});

it("keeps portable program hashes, complete closures and decisions equal across all foundations", () => {
  const directory = mkdtempSync(join(tmpdir(), "portable-policy-"));
  try {
    const initial = [
      f("ResourceType", "item", "artifact"),
      f("ResourceState", "item", "draft"),
      f("AllowedTransition", "artifact", "apply", "draft", "done"),
      f("Capability", "operator", "item", "apply"),
      f("Source", "origin", "input"),
      f("DependsOn", "item", "input"),
      f("Grant", "operator", "item"),
      f("Version", "item", "v1"),
    ];
    const combined: RuntimeBinding = {
      ...binding,
      mechanisms: ["capability", "provenance", "fsm"],
      fsmActions: ["apply"],
      predicates: {
        ...binding.predicates,
        ...CAPABILITY_PREDICATES,
        ...PROVENANCE_PREDICATES,
        ...Object.fromEntries(
          Object.entries(LIFECYCLE_PREDICATES).map(([k, v]) => [
            k,
            { kind: v.kind, args: v.args, meaning: k },
          ]),
        ),
      },
      tests: binding.tests.map((test) => ({
        ...test,
        inputs: [
          ...initial.filter((fact) => !["Grant", "Version"].includes(fact.predicate)),
          ...test.inputs,
        ],
      })),
    };
    const fixtures = [];
    for (const [name, contract, inputs, intent] of [
      [
        "simple",
        binding,
        [f("Grant", "operator", "item"), f("Version", "item", "v1")],
        binding.tests[0]!.request,
      ],
      [
        "declared-policy",
        binding,
        [f("Grant", "operator", "item"), f("Version", "item", "v1")],
        binding.tests[0]!.request,
      ],
      ["all-foundations", combined, initial, binding.tests[0]!.request],
      [
        "capability-revoked",
        combined,
        initial.filter((fact) => fact.predicate !== "Capability"),
        binding.tests[0]!.request,
      ],
      [
        "uppercase-symbols",
        binding,
        [f("Grant", "UPPERCASE", "中文😀"), f("Version", "中文😀", 'quote"\n')],
        {
          actor: "UPPERCASE",
          action: "apply",
          resource: "中文😀",
          parameters: { version: 'quote"\n' },
        },
      ],
    ] as const) {
      const source =
        name === "declared-policy"
          ? `.decl Grant(Actor:symbol, Resource:symbol)\n.input Grant\n${policy}`
          : policy;
      const installed = contract.mechanisms?.includes("capability")
        ? `${source}\nDeny(Q, "no_grant") :- Request(Q, P, E), Parameter(Q, "resource", R), not Can(P, R, E).`
        : source;
      const bundle = compileApplicationPolicy(contract, installed);
      const session = createPolicySession(contract, bundle, [...inputs]);
      const closure = Object.entries(contract.predicates).flatMap(([predicate, schema]) => {
        // Query all declared relations; transient requests are absent in the snapshot.
        const args = schema.args.map((_, i) => `V${i}`).join(", ");
        return session
          .query(`?- ${predicate}(${args}).`)
          .rows.map((row) => JSON.stringify([predicate, ...row]));
      });
      fixtures.push({
        name,
        binding: contract,
        source: installed,
        hash: bundle.hash,
        inputs,
        request: intent,
        allowed: session.check(intent).allowed,
        closure,
      });
    }
    const config = join(directory, "fixtures.json");
    writeFileSync(config, JSON.stringify(fixtures));
    const result = spawnSync(
      "python3",
      [fileURLToPath(new URL("../python/tests/portable.py", import.meta.url)), config],
      { encoding: "utf8", timeout: 25_000 },
    );
    expect(result.status, result.stderr).toBe(0);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});
