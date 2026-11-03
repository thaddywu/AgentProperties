import { createBackendPort } from "@rakazo/policy-runtime/backend-port";
import type { PolicyFact } from "@rakazo/policy-runtime/datalog";
import { factKey } from "@rakazo/policy-runtime/datalog";
import { novaMessagingProfile } from "../ports.js";
import type { NovaPolicyArtifact } from "../translated-policy.js";
import { NOVA_TAGS } from "./oracle.js";

type Intent = { from: string; to: string; revokeA: boolean };
const departments = ["procurement", "facility", "hr"];
const principals = [...departments, "auditor_a", "auditor_b", "board"];
const select = (facts: PolicyFact[], names: string[]) =>
  facts
    .filter((f) => names.includes(f.predicate))
    .map(factKey)
    .sort();

/** Identical seeded intent traces through real ports; no agent-side EDB injection. */
export async function testNovaTraces(
  policy: NovaPolicyArtifact,
  options: { seed: number; traces: number; steps: number },
) {
  if (
    ![options.seed, options.traces, options.steps].every(Number.isSafeInteger) ||
    options.seed < 0 ||
    options.seed > 0xffffffff ||
    options.traces < 1 ||
    options.traces > 1000 ||
    options.steps < 1 ||
    options.steps > 100
  )
    throw new Error("Choose a 32-bit seed, 1–1,000 traces and 1–100 steps.");
  let state = options.seed,
    checkedSteps = 0,
    rejected = 0;
  const random = () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 0x100000000;
  };
  const counterexamples: unknown[] = [];
  for (let trace = 0; trace < options.traces; trace++) {
    const missingGroup = trace % 2 === 1;
    let revokeA = false;
    const create = (translated: boolean) => {
      const profile = novaMessagingProfile(translated ? policy : undefined);
      if (missingGroup)
        profile.configuration = profile.configuration.filter(
          (f) => !(f.predicate === "TagGroup" && f.args[0] === "nova_hiring"),
        );
      const grants = profile.configuration.filter((f) => f.predicate === "AgentHasCapability");
      const released: string[] = [];
      const port = createBackendPort({
        profile,
        observations: [
          {
            id: "grants",
            scope: "nova",
            predicates: ["AgentHasCapability"],
            read: async () => ({
              version: revokeA ? "revoked" : "initial",
              complete: true,
              facts: grants.filter((f) => !revokeA || f.args[0] !== "auditor_a"),
            }),
          },
        ],
        deliver: async (m) => {
          released.push(m.id);
        },
      });
      return { port, released };
    };
    const a = create(false),
      b = create(true);
    for (const [i, department] of departments.entries())
      for (const target of [a, b])
        await target.port.ingest({
          authority: "board",
          recipient: department,
          id: `source${i}`,
          body: "synthetic source",
          tag: NOVA_TAGS[i]!,
        });
    const prefix: Intent[] = [];
    for (let step = 0; step < options.steps; step++) {
      const intent: Intent =
        step < 3
          ? { from: departments[step]!, to: step === 1 ? "auditor_b" : "auditor_a", revokeA: false }
          : step < 7
            ? {
                from: step % 2 ? "procurement" : "board",
                to: step % 2 ? "board" : step === 6 ? "auditor_a" : "procurement",
                revokeA: false,
              }
            : (() => {
                const from = principals[Math.floor(random() * principals.length)]!;
                const recipients = principals.filter((p) => p !== from);
                return {
                  from,
                  to: recipients[Math.floor(random() * recipients.length)]!,
                  revokeA: random() < 0.25,
                };
              })();
      revokeA = intent.revokeA;
      prefix.push(intent);
      const left = await a.port.bind(intent.from).send(intent.to, `m${step}`, "synthetic relay");
      const right = await b.port.bind(intent.from).send(intent.to, `m${step}`, "synthetic relay");
      checkedSteps++;
      if (!left.allowed) rejected++;
      const observe = (target: typeof a) => ({
        released: target.released,
        facts: select(target.port.inspect().facts, ["Knows", "Covered", "Finished"]),
      });
      const ref = observe(a),
        trans = observe(b);
      if (left.allowed !== right.allowed || JSON.stringify(ref) !== JSON.stringify(trans)) {
        counterexamples.push({
          trace,
          missingGroup,
          prefix: [...prefix],
          reference: { allowed: left.allowed, ...ref },
          translated: { allowed: right.allowed, ...trans },
        });
        break; // First differing prefix, rather than continuing already-diverged worlds.
      }
    }
  }
  return {
    status: counterexamples.length ? "different" : "tested_no_difference",
    ...options,
    checkedSteps,
    rejected,
    tracesWithDifference: counterexamples.length,
    counterexamples,
    scope:
      "Actual shared-port executions: fixed and missing-hiring-group configurations, legal split prefix, seeded relays/cycles and authoritative grant refresh/revocation. No direct receipt/tag assertion. These traces are exploratory, not exhaustive or held-out.",
  };
}
