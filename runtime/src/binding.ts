import type { PolicyFact } from "./datalog.js";
import { LIFECYCLE_PREDICATES } from "./lifecycle.js";

export type ActionIntent = { actor: string; action: string; resource: string };
export type RuntimeBinding = {
  version: 1;
  id: string;
  context: string;
  predicates: Record<string, { kind: "input" | "derived"; args: string[]; meaning: string }>;
  decision: { request: string; allow: string; deny: string };
  mechanisms?: "fsm"[];
  tests: { name: string; inputs: PolicyFact[]; request: ActionIntent; allowed: boolean }[];
};

const name = /^[A-Za-z][A-Za-z_0-9]*$/;
const object = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object" && !Array.isArray(value);

export function validateIntent(value: unknown): asserts value is ActionIntent {
  if (
    !object(value) ||
    !["actor", "action", "resource"].every(
      (key) => typeof value[key] === "string" && value[key].length > 0 && value[key].length <= 1024,
    )
  )
    throw new Error("An action needs bounded, nonempty actor, action and resource strings.");
}

/** Adapter-owned instrumentation contract, never model output or authority inferred from Markdown. */
export function readRuntimeBinding(value: unknown): RuntimeBinding {
  if (
    !object(value) ||
    value.version !== 1 ||
    typeof value.id !== "string" ||
    !/^[a-z][a-z0-9-]{0,63}$/.test(value.id) ||
    typeof value.context !== "string" ||
    !value.context.trim() ||
    value.context.length > 12_000 ||
    !object(value.predicates) ||
    !object(value.decision) ||
    !Array.isArray(value.tests)
  )
    throw new Error("Invalid version-1 runtime binding.");
  const predicates = Object.entries(value.predicates);
  if (!predicates.length || predicates.length > 64) throw new Error("Invalid predicate count.");
  for (const [predicate, schema] of predicates) {
    if (
      !name.test(predicate) ||
      ["QueryResult", "RuntimeSentinel"].includes(predicate) ||
      !object(schema) ||
      !["input", "derived"].includes(String(schema.kind)) ||
      !Array.isArray(schema.args) ||
      schema.args.length > 8 ||
      !schema.args.every((arg) => typeof arg === "string" && name.test(arg)) ||
      typeof schema.meaning !== "string" ||
      !schema.meaning.trim() ||
      schema.meaning.length > 2000
    )
      throw new Error(`Invalid predicate declaration: ${predicate}`);
  }
  const decision = value.decision;
  if (new Set(Object.values(decision)).size !== 3) throw new Error("Gate predicates must differ.");
  for (const [slot, kind, arity] of [
    ["request", "input", 4],
    ["allow", "derived", 1],
    ["deny", "derived", 2],
  ] as const) {
    const predicate = decision[slot];
    const schema =
      typeof predicate === "string" && Object.hasOwn(value.predicates, predicate)
        ? value.predicates[predicate]
        : undefined;
    if (
      !object(schema) ||
      schema.kind !== kind ||
      !Array.isArray(schema.args) ||
      schema.args.length !== arity
    )
      throw new Error(`Invalid ${slot} gate declaration.`);
  }
  if (
    value.tests.length < 2 ||
    value.tests.length > 100 ||
    !value.tests.some((test) => object(test) && test.allowed === true) ||
    !value.tests.some((test) => object(test) && test.allowed === false)
  )
    throw new Error("Binding needs independent allow and deny acceptance cases (2–100 total).");
  const binding = structuredClone(value) as RuntimeBinding;
  if (value.mechanisms !== undefined) {
    if (
      !Array.isArray(value.mechanisms) ||
      value.mechanisms.length !== 1 ||
      value.mechanisms[0] !== "fsm"
    )
      throw new Error("The action SDK supports the optional fsm mechanism.");
    for (const [predicate, expected] of Object.entries(LIFECYCLE_PREDICATES)) {
      const schema = binding.predicates[predicate];
      if (!schema || schema.kind !== expected.kind || schema.args.length !== expected.args.length)
        throw new Error(
          `FSM binding must declare ${predicate}/${expected.args.length} as ${expected.kind}.`,
        );
    }
  }
  const names = new Set<string>();
  for (const test of binding.tests) {
    if (
      !object(test) ||
      typeof test.name !== "string" ||
      !test.name.trim() ||
      names.has(test.name) ||
      typeof test.allowed !== "boolean"
    )
      throw new Error("Invalid or duplicate acceptance case.");
    names.add(test.name);
    validateIntent(test.request);
    validateInputs(binding, test.inputs);
  }
  return binding;
}

export function validateInputs(
  binding: RuntimeBinding,
  facts: unknown,
): asserts facts is PolicyFact[] {
  if (!Array.isArray(facts) || facts.length > 5000) throw new Error("At most 5000 input facts.");
  for (const fact of facts) {
    const schema =
      object(fact) &&
      typeof fact.predicate === "string" &&
      Object.hasOwn(binding.predicates, fact.predicate)
        ? binding.predicates[fact.predicate]
        : undefined;
    if (
      schema?.kind !== "input" ||
      fact.predicate === binding.decision.request ||
      !Array.isArray(fact.args) ||
      fact.args.length !== schema.args.length ||
      !fact.args.every((arg: unknown) => typeof arg === "string" && arg.length <= 4096)
    )
      throw new Error(
        "Only declared, non-request input facts may be supplied by the trusted adapter.",
      );
  }
}
