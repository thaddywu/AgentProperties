import type { PolicyFact } from "./datalog.js";
import { FOUNDATIONS } from "./foundations.js";
import { LIFECYCLE_PREDICATES } from "./lifecycle.js";

export type ActionIntent = {
  actor: string;
  action: string;
  resource?: string;
  parameters?: Record<string, string>;
};
export type RuntimeBinding = {
  version: 1;
  id: string;
  context: string;
  predicates: Record<
    string,
    {
      kind: "input" | "derived";
      args: string[];
      meaning: string;
      key?: string[];
      types?: ("symbol" | "number")[];
    }
  >;
  decision: { request: string; allow: string; deny: string; parameters?: string };
  mechanisms?: ("fsm" | keyof typeof FOUNDATIONS)[];
  /** Omitted means every operation requires an FSM transition, as in the original API. */
  fsmActions?: string[];
  /** The backend-authoritative execution profile is implemented by the Python runtime. */
  fsmState?: "runtime" | "backend";
  fsmTarget?: string;
  configuration?: PolicyFact[];
  invariants?: string[];
  tests: { name: string; inputs: PolicyFact[]; request: ActionIntent; allowed: boolean }[];
};

const name = /^[A-Za-z][A-Za-z_0-9]*$/;
const object = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object" && !Array.isArray(value);

export function validateIntent(value: unknown): asserts value is ActionIntent {
  if (
    !object(value) ||
    !["actor", "action"].every(
      (key) => typeof value[key] === "string" && value[key].length > 0 && value[key].length <= 1024,
    )
  )
    throw new Error("An action needs bounded, nonempty actor, action and resource strings.");
  if (
    value.resource !== undefined &&
    (typeof value.resource !== "string" || !value.resource.length || value.resource.length > 1024)
  )
    throw new Error("A supplied resource must be a bounded nonempty string.");
  if (
    value.parameters !== undefined &&
    (!object(value.parameters) ||
      Object.keys(value.parameters).length > 32 ||
      Object.entries(value.parameters).some(
        ([key, term]) =>
          !name.test(key) || key.length > 64 || typeof term !== "string" || term.length > 4096,
      ))
  )
    throw new Error("Action parameters need at most 32 named, bounded string values.");
}

export const INTERNAL_PREDICATES: string[] = [];

/** Adapter-owned instrumentation contract, never model output or authority inferred from Markdown. */
export function readRuntimeBinding(value: unknown): RuntimeBinding {
  if (
    object(value) &&
    object(value.decision) &&
    object(value.predicates) &&
    value.decision.parameters === undefined
  ) {
    const copy = structuredClone(value);
    (copy.decision as Record<string, unknown>).parameters = "Parameter";
    const predicates = copy.predicates as Record<string, unknown>;
    predicates.Parameter ??= {
      kind: "input",
      args: ["Q", "Name", "Value"],
      meaning: "Runtime-bound request argument.",
    };
    value = copy;
  }
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
      ["QueryResult", "RuntimeSentinel", ...INTERNAL_PREDICATES].includes(predicate) ||
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
    if (
      schema.key !== undefined &&
      (schema.kind !== "input" ||
        !Array.isArray(schema.key) ||
        new Set(schema.key).size !== schema.key.length ||
        schema.key.some((field) => !(schema.args as string[]).includes(field as string)))
    )
      throw new Error(`Invalid input key declaration: ${predicate}`);
    if (
      schema.types !== undefined &&
      (!Array.isArray(schema.types) ||
        schema.types.length !== schema.args.length ||
        schema.types.some((type) => type !== "symbol" && type !== "number"))
    )
      throw new Error(`Invalid predicate field types: ${predicate}`);
  }
  const decision = value.decision;
  if (
    Object.keys(decision).some(
      (key) => !["request", "allow", "deny", "parameters"].includes(key),
    ) ||
    new Set(Object.values(decision)).size !== Object.values(decision).length
  )
    throw new Error("Gate predicates must differ.");
  for (const [slot, kind, arity] of [
    ["request", "input", 3],
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
  if (decision.parameters !== undefined) {
    const schema =
      typeof decision.parameters === "string" &&
      Object.hasOwn(value.predicates, decision.parameters)
        ? value.predicates[decision.parameters]
        : undefined;
    if (
      !object(schema) ||
      schema.kind !== "input" ||
      !Array.isArray(schema.args) ||
      schema.args.length !== 3
    )
      throw new Error("Parameter input must have request, name and value arguments.");
  }
  if (
    (value.tests.length > 0 && value.tests.length < 2) ||
    value.tests.length > 100 ||
    (value.tests.length > 0 &&
      !value.tests.some((test) => object(test) && test.allowed === true)) ||
    (value.tests.length > 0 && !value.tests.some((test) => object(test) && test.allowed === false))
  )
    throw new Error("Binding needs independent allow and deny acceptance cases (2–100 total).");
  const binding = structuredClone(value) as RuntimeBinding;
  if (
    binding.fsmTarget !== undefined &&
    (!binding.mechanisms?.includes("fsm") || !name.test(binding.fsmTarget))
  )
    throw new Error("FSM target must name a request parameter.");
  if (
    !Array.isArray(binding.invariants ?? []) ||
    binding.invariants?.some((predicate) => binding.predicates[predicate]?.kind !== "derived")
  )
    throw new Error("Invariants must name declared derived relations that remain empty.");
  validateInputs(binding, binding.configuration ?? []);
  if (value.mechanisms !== undefined) {
    if (
      !Array.isArray(value.mechanisms) ||
      !value.mechanisms.length ||
      new Set(value.mechanisms).size !== value.mechanisms.length ||
      value.mechanisms.some(
        (mechanism) => mechanism !== "fsm" && !Object.hasOwn(FOUNDATIONS, mechanism),
      )
    )
      throw new Error("Select distinct supported policy mechanisms.");
    const selected = [
      ...(binding.mechanisms!.includes("fsm") ? [LIFECYCLE_PREDICATES] : []),
      ...Object.entries(FOUNDATIONS)
        .filter(([mechanism]) =>
          binding.mechanisms!.includes(mechanism as keyof typeof FOUNDATIONS),
        )
        .map(([, foundation]) => foundation.predicates),
    ];
    const mechanismNames = new Set(selected.flatMap((predicates) => Object.keys(predicates)));
    if (Object.values(binding.decision).some((predicate) => mechanismNames.has(predicate)))
      throw new Error("Gate and parameter relations cannot overlap selected mechanism predicates.");
    for (const [predicate, expected] of selected.flatMap((predicates) =>
      Object.entries(predicates),
    )) {
      const schema = binding.predicates[predicate];
      if (!schema || schema.kind !== expected.kind || schema.args.length !== expected.args.length)
        throw new Error(
          `Mechanism binding must declare ${predicate}/${expected.args.length} as ${expected.kind}.`,
        );
    }
  }
  if (
    value.fsmActions !== undefined &&
    (!binding.mechanisms?.includes("fsm") ||
      !Array.isArray(value.fsmActions) ||
      value.fsmActions.length > 64 ||
      new Set(value.fsmActions).size !== value.fsmActions.length ||
      !value.fsmActions.every(
        (action) => typeof action === "string" && action.length > 0 && action.length <= 1024,
      ))
  )
    throw new Error("FSM actions must be a nonempty, distinct list on an FSM binding.");
  const names = new Set<string>();
  if (
    value.fsmState !== undefined &&
    (!binding.mechanisms?.includes("fsm") ||
      !["runtime", "backend"].includes(String(value.fsmState)))
  )
    throw new Error("FSM state authority must be runtime or backend on an FSM binding.");
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
      [binding.decision.request, binding.decision.parameters].includes(fact.predicate) ||
      !Array.isArray(fact.args) ||
      fact.args.length !== schema.args.length ||
      !fact.args.every((arg: unknown) => typeof arg === "string" && arg.length <= 4096)
    )
      throw new Error(
        "Only declared, non-request input facts may be supplied by the trusted adapter.",
      );
    schema.args.forEach((_name, index) => {
      if (schema.types?.[index] !== "number") return;
      const raw = fact.args[index] as string;
      if (
        !/^(?:0|-?[1-9][0-9]*)$/.test(raw) ||
        raw.length > 20 ||
        BigInt(raw) < -(2n ** 63n) ||
        BigInt(raw) >= 2n ** 63n
      )
        throw new Error("Numeric facts require canonical signed 64-bit integers.");
    });
  }
  for (const [name, schema] of Object.entries(binding.predicates)) {
    if (schema.key === undefined) continue;
    const seen = new Map<string, string>();
    for (const row of facts as PolicyFact[]) {
      if (row.predicate !== name) continue;
      const key = JSON.stringify(schema.key.map((field) => row.args[schema.args.indexOf(field)]));
      const value = JSON.stringify(row.args);
      if (seen.has(key) && seen.get(key) !== value)
        throw new Error(`Conflicting keyed input: ${name}`);
      seen.set(key, value);
    }
  }
}
