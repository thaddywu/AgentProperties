import { createHash, randomUUID } from "node:crypto";
import type { ActionIntent, RuntimeBinding } from "./binding.js";
import { readRuntimeBinding, validateInputs, validateIntent } from "./binding.js";
import type { PolicyFact, Rule } from "./datalog.js";
import { evaluateDatalog, factKey } from "./datalog.js";
import { FOUNDATIONS } from "./foundations.js";
import {
  LIFECYCLE_INPUT_ARITIES,
  LIFECYCLE_PREDICATES,
  LIFECYCLE_RULES,
  validateLifecycleInputs,
} from "./lifecycle.js";
import type { ObservationSnapshot } from "./observations.js";
import { readPolicyDocument } from "./policy-source.js";
import {
  decode,
  encodeFact,
  encodeRule,
  limits,
  parsePolicyRules,
  parseProgram,
  validateAndStratify,
} from "./query.js";

export type PolicyBundle = { version: 2; binding: RuntimeBinding; source: string; hash: string };
export type Explanation = {
  fact: PolicyFact;
  rule?: string;
  premises: Explanation[];
  truncated?: boolean;
  checks?: { kind: "absence" | "comparison"; text: string }[];
};
export type ActionDecision = {
  allowed: boolean;
  policyHash: string;
  request: ActionIntent & { id: string };
  reasons: string[];
  evidence: Explanation[];
  transition?: { resource: string; from: string; to: string };
  observationVersions?: Record<string, string>;
};

export type ActionContext = Readonly<{
  request: Readonly<
    Omit<ActionIntent, "parameters"> & { id: string; parameters?: Readonly<Record<string, string>> }
  >;
  policyHash: string;
}>;
export type InputSnapshot = ObservationSnapshot & {
  id: string;
  predicates: string[];
};
export type EffectOutcome<T> =
  | { status: "applied"; value: T; observations?: PolicyFact[] }
  | { status: "not_applied"; reason: string }
  | { status: "unknown" };
/** Must hold the backend's serialization/snapshot boundary through effect and confirmed commit. */
export type ActionTransaction = <T>(
  context: ActionContext,
  run: () => Promise<ExecutionResult<T>>,
) => Promise<unknown>;
export type ObservedExecution<T> = {
  observe?: (context: ActionContext) => Promise<InputSnapshot[]>;
  effect: (context: ActionContext) => Promise<EffectOutcome<T>>;
  transaction?: ActionTransaction;
};
export type ExecutionResult<T> =
  | { allowed: false; decision: ActionDecision }
  | { allowed: true; decision: ActionDecision; value: T };

/** A trusted effect adapter may certify that a failed call produced no external effect. */
export class EffectNotAppliedError extends Error {}
export class EffectUncertainError extends Error {
  constructor(public readonly attemptId: string) {
    super("Execution was not confirmed; this session is stopped.");
  }
}
const hasFsm = (binding: RuntimeBinding) => binding.mechanisms?.includes("fsm") === true;
const needsTransition = (binding: RuntimeBinding, action: string) =>
  hasFsm(binding) && (!binding.fsmActions || binding.fsmActions.includes(action));
const lifecycleInput = (fact: PolicyFact) => Object.hasOwn(LIFECYCLE_INPUT_ARITIES, fact.predicate);

function parsePolicy(binding: RuntimeBinding, source: string) {
  const parsed = readPolicyDocument(source);
  if (
    parsed.configuration.some(
      (fact) => !binding.configuration?.some((allowed) => factKey(allowed) === factKey(fact)),
    )
  )
    throw new Error("Static policy facts do not match the reviewed configuration.");
  for (const [name, schema] of Object.entries(parsed.predicates)) {
    const expected = Object.hasOwn(binding.predicates, name) ? binding.predicates[name] : undefined;
    if (
      !expected ||
      schema.kind !== expected.kind ||
      canonical(schema.args) !== canonical(expected.args)
    )
      throw new Error("Policy declarations do not match the trusted binding.");
    if (canonical(schema.key ?? null) !== canonical(expected.key ?? null))
      throw new Error("Policy keys do not match the trusted binding.");
    if (
      canonical(schema.types ?? schema.args.map(() => "symbol")) !==
      canonical(expected.types ?? expected.args.map(() => "symbol"))
    )
      throw new Error("Policy field types do not match the trusted binding.");
  }
  const rules = parsePolicyRules(parsed.rules);
  if (!rules.length) throw new Error("Policy contains no rules.");
  for (const rule of rules) {
    for (const atom of [rule.head, ...rule.body]) {
      const schema = Object.hasOwn(binding.predicates, atom.predicate)
        ? binding.predicates[atom.predicate]
        : undefined;
      if (!schema || schema.args.length !== atom.args.length)
        throw new Error(`Unknown predicate or wrong arity: ${atom.predicate}`);
    }
    if (binding.predicates[rule.head.predicate]!.kind !== "derived")
      throw new Error(`Policy cannot write runtime input: ${rule.head.predicate}`);
    if (
      (hasFsm(binding) && Object.hasOwn(LIFECYCLE_PREDICATES, rule.head.predicate)) ||
      Object.entries(FOUNDATIONS).some(
        ([name, foundation]) =>
          binding.mechanisms?.includes(name as keyof typeof FOUNDATIONS) &&
          Object.hasOwn(foundation.predicates, rule.head.predicate),
      )
    )
      throw new Error(
        `Policy cannot replace selected mechanism foundation: ${rule.head.predicate}`,
      );
  }
  const foundation = hasFsm(binding) ? [...LIFECYCLE_RULES] : [];
  for (const [name, selected] of Object.entries(FOUNDATIONS))
    if (binding.mechanisms?.includes(name as keyof typeof FOUNDATIONS))
      foundation.push(...selected.rules);
  const combined = foundation.map(encodeRule).concat(rules);
  validateAndStratify([], combined);
  return combined;
}

function evaluate(inputs: PolicyFact[], rules: Rule[]) {
  return evaluateDatalog(inputs.map(encodeFact), rules, limits);
}
function explain(
  result: ReturnType<typeof evaluate>,
  fact: PolicyFact,
  budget = { nodes: 512 },
  depth = 0,
): Explanation {
  const decoded = { predicate: fact.predicate, args: fact.args.map(decode) };
  const proof = result.proofs.get(factKey(fact));
  if (depth >= 32 || budget.nodes-- <= 0) return { fact: decoded, premises: [], truncated: true };
  if (!proof) return { fact: decoded, premises: [] };
  const premises: Explanation[] = [];
  for (const premise of proof.premises) {
    if (budget.nodes <= 0) break;
    premises.push(explain(result, premise, budget, depth + 1));
  }
  return {
    fact: decoded,
    rule: proof.rule,
    premises,
    ...(premises.length < proof.premises.length ? { truncated: true } : {}),
    checks: proof.checks,
  };
}

function decide(
  binding: RuntimeBinding,
  hash: string,
  rules: Rule[],
  inputs: PolicyFact[],
  intent: ActionIntent,
  requestId = randomUUID(),
): ActionDecision {
  validateIntent(intent);
  if (Object.keys(intent.parameters ?? {}).length && !binding.decision.parameters)
    throw new Error("This binding does not declare request parameters.");
  const request = { ...structuredClone(intent), id: requestId };
  const requestArgs = [request.id, request.actor, request.action];
  const parameters = { ...intent.parameters };
  if (intent.resource !== undefined) {
    if (parameters.resource !== undefined && parameters.resource !== intent.resource)
      throw new Error("Conflicting resource parameter.");
    parameters.resource = intent.resource;
  }
  const resource = intent.resource ?? parameters[binding.fsmTarget ?? "resource"];
  const result = evaluate(
    [
      ...inputs,
      {
        predicate: binding.decision.request,
        args: requestArgs,
      },
      ...Object.entries(parameters).map(([key, value]) => ({
        predicate: binding.decision.parameters!,
        args: [request.id, key, value],
      })),
    ],
    rules,
  );
  const transitionFact = needsTransition(binding, intent.action)
    ? result.facts.find(
        (fact) =>
          fact.predicate === "CanTransition" &&
          decode(fact.args[0]!) === resource &&
          decode(fact.args[1]!) === intent.action,
      )
    : undefined;
  if (needsTransition(binding, intent.action) && !transitionFact)
    result.facts.push(
      encodeFact({ predicate: binding.decision.deny, args: [request.id, "invalid_transition"] }),
    );
  if (result.facts.some((fact) => binding.invariants?.includes(fact.predicate)))
    result.facts.push(
      encodeFact({ predicate: binding.decision.deny, args: [request.id, "invariant_violation"] }),
    );
  const evidence = result.facts.filter(
    (fact) =>
      [binding.decision.allow, binding.decision.deny].includes(fact.predicate) &&
      decode(fact.args[0]!) === request.id,
  );
  const denials = evidence.filter((fact) => fact.predicate === binding.decision.deny);
  const allowed =
    denials.length === 0 && evidence.some((fact) => fact.predicate === binding.decision.allow);
  const budget = { nodes: 512 };
  const transition = allowed ? transitionFact : undefined;
  return {
    allowed,
    policyHash: hash,
    request,
    reasons: denials.length
      ? denials.map((fact) => decode(fact.args[1]!))
      : allowed
        ? []
        : ["no_explicit_allow"],
    evidence: evidence.map((fact) => explain(result, fact, budget)),
    ...(transition
      ? {
          transition: {
            resource: resource!,
            from: decode(transition.args[2]!),
            to: decode(transition.args[3]!),
          },
        }
      : {}),
  };
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object")
    return `{${Object.entries(value)
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
      .join(",")}}`;
  return JSON.stringify(value);
}

/** Static validation plus app-owned acceptance cases, not a proof of semantic equivalence. */
export function compileApplicationPolicy(bindingInput: unknown, source: string): PolicyBundle {
  const binding = readRuntimeBinding(bindingInput);
  const rules = parsePolicy(binding, source);
  const hash = createHash("sha256")
    .update(canonical({ version: 2, binding, source, rules }))
    .digest("hex");
  for (const test of binding.tests) {
    if (hasFsm(binding))
      validateLifecycleInputs(test.inputs.filter(lifecycleInput), binding.fsmActions);
    const decision = decide(binding, hash, rules, test.inputs, test.request);
    if (decision.allowed !== test.allowed) throw new Error(`Acceptance case failed: ${test.name}`);
  }
  return { version: 2, binding, source, hash };
}

/** In-process trusted-adapter boundary; callers never hand a decision token back to execute. */
export function createPolicySession(
  bindingInput: unknown,
  bundleInput: PolicyBundle,
  initialInputs: PolicyFact[] = [],
) {
  if (readRuntimeBinding(bindingInput).fsmState === "backend")
    throw new Error("Backend-authoritative FSM execution requires the Python runtime.");
  if (bundleInput.version !== 2)
    throw new Error("Unsupported policy bundle version; recompile with the trusted binding.");
  const bundle = compileApplicationPolicy(bindingInput, bundleInput.source);
  if (bundle.hash !== bundleInput.hash) throw new Error("Policy bundle hash mismatch.");
  if (canonical(bundle.binding) !== canonical(bundleInput.binding))
    throw new Error("Policy bundle binding mismatch.");
  const binding = bundle.binding;
  const rules = parsePolicy(binding, bundle.source);
  let inputs: PolicyFact[] = [];
  let pending = 0;
  let queue: Promise<unknown> = Promise.resolve();
  let failed = false;
  const protectedInputs = (facts: PolicyFact[]) =>
    [...new Set(facts.filter(lifecycleInput).map(factKey))].sort();
  const checked = (facts: PolicyFact[]) => {
    validateInputs(binding, facts);
    const copy = structuredClone(facts);
    if (hasFsm(binding)) validateLifecycleInputs(copy.filter(lifecycleInput), binding.fsmActions);
    const closure = evaluate(copy, rules); // Reject invalid snapshots before any external effect.
    if (closure.facts.some((fact) => binding.invariants?.includes(fact.predicate)))
      throw new Error("An application invariant was violated.");
    return copy;
  };
  inputs = checked(initialInputs);
  const exclusive = <T>(operation: () => Promise<T>): Promise<T> => {
    pending++;
    const run = queue.then(async () => {
      try {
        return await operation();
      } finally {
        pending--;
      }
    });
    queue = run.catch(() => {});
    return run;
  };
  const idle = () => {
    if (pending)
      throw new Error("Session has an in-flight operation; await it before inspecting state.");
  };
  const validateCommit = (facts: PolicyFact[]) => {
    validateInputs(binding, facts);
    if (hasFsm(binding) && facts.some(lifecycleInput))
      throw new Error("Successful FSM transitions are committed only by the runtime.");
  };
  const refresh = (current: PolicyFact[], snapshots: InputSnapshot[]) => {
    if (!Array.isArray(snapshots) || snapshots.length > 64)
      throw new Error("Invalid observation snapshots.");
    const replaced = new Set<string>();
    const versions: Record<string, string> = Object.create(null);
    const facts: PolicyFact[] = [];
    for (const snapshot of snapshots) {
      if (
        !snapshot ||
        typeof snapshot.id !== "string" ||
        !snapshot.id.length ||
        snapshot.id.length > 1024 ||
        Object.hasOwn(versions, snapshot.id) ||
        typeof snapshot.version !== "string" ||
        !snapshot.version.trim() ||
        snapshot.version.length > 1024 ||
        snapshot.complete !== true ||
        !Array.isArray(snapshot.predicates) ||
        !snapshot.predicates.length ||
        snapshot.predicates.some(
          (predicate) =>
            typeof predicate !== "string" ||
            replaced.has(predicate) ||
            binding.predicates[predicate]?.kind !== "input" ||
            [binding.decision.request, binding.decision.parameters].includes(predicate) ||
            (hasFsm(binding) && Object.hasOwn(LIFECYCLE_INPUT_ARITIES, predicate)),
        )
      )
        throw new Error(
          "Observations need distinct declared inputs and complete, versioned sources.",
        );
      validateInputs(binding, snapshot.facts);
      if (
        new Set(snapshot.predicates).size !== snapshot.predicates.length ||
        snapshot.facts.some((fact) => !snapshot.predicates.includes(fact.predicate))
      )
        throw new Error("An observation source wrote an undeclared relation.");
      for (const predicate of snapshot.predicates) replaced.add(predicate);
      versions[snapshot.id] = snapshot.version;
      facts.push(...structuredClone(snapshot.facts));
    }
    return {
      facts: checked([...current.filter((fact) => !replaced.has(fact.predicate)), ...facts]),
      versions,
    };
  };
  const execute = <T>(
    intent: ActionIntent,
    options: ObservedExecution<T>,
    commitInputs: PolicyFact[] = [],
  ): Promise<ExecutionResult<T>> => {
    validateIntent(intent);
    validateCommit(commitInputs);
    const captured = structuredClone({ intent, commitInputs });
    const { observe, effect, transaction } = options;
    return exclusive(async () => {
      const request = Object.freeze({
        ...captured.intent,
        id: randomUUID(),
        ...(captured.intent.parameters
          ? { parameters: Object.freeze(captured.intent.parameters) }
          : {}),
      });
      const context: ActionContext = Object.freeze({ request, policyHash: bundle.hash });
      if (failed)
        throw new Error("An earlier execution was not confirmed; this session is stopped.");
      let staged: PolicyFact[] | undefined;
      let decision: ActionDecision | undefined;
      let observations = captured.commitInputs;
      let effectStarted = false;
      let entered = false;
      let transactionActive = true;
      let produced: ExecutionResult<T> | undefined;
      const run = async (): Promise<ExecutionResult<T>> => {
        if (entered || !transactionActive)
          throw new Error("A transaction must invoke its operation exactly once before returning.");
        entered = true;
        const snapshot = refresh(inputs, observe ? await observe(context) : []);
        if (!transactionActive)
          throw new Error("The backend transaction ended before observation completed.");
        decision = decide(binding, bundle.hash, rules, snapshot.facts, captured.intent, request.id);
        if (Object.keys(snapshot.versions).length) decision.observationVersions = snapshot.versions;
        if (!decision.allowed) {
          staged = snapshot.facts;
          produced = { allowed: false, decision };
          return produced;
        }
        if (needsTransition(binding, captured.intent.action) && !decision.transition)
          throw new Error("Missing validated current transition.");
        const next = (commits: PolicyFact[]) =>
          checked(
            decision!.transition
              ? transitionInputs(snapshot.facts, decision!.transition, commits)
              : [...snapshot.facts, ...commits],
          );
        next(observations); // Validate known commits and resource bounds before touching the backend.
        effectStarted = true;
        const outcome = await effect(context);
        if (outcome?.status === "not_applied") throw new EffectNotAppliedError(outcome.reason);
        if (outcome?.status !== "applied") throw new Error("External outcome is uncertain.");
        const committed = structuredClone(outcome.observations ?? []);
        validateCommit(committed);
        observations = [...observations, ...committed];
        staged = next(observations);
        produced = { allowed: true, decision, value: outcome.value };
        return produced;
      };
      try {
        if (transaction) await transaction(context, run);
        else await run();
        transactionActive = false;
        if (!produced || !staged)
          throw new Error(
            "A transaction must await its operation and confirm commit before returning.",
          );
        inputs = staged;
        return produced;
      } catch (error) {
        transactionActive = false;
        if (effectStarted && !(error instanceof EffectNotAppliedError)) {
          failed = true;
          throw new EffectUncertainError(request.id);
        }
        throw error;
      }
    });
  };
  return {
    policyHash: bundle.hash,
    snapshot: () => {
      idle();
      return structuredClone(inputs);
    },
    replaceInputs(facts: PolicyFact[]) {
      validateInputs(binding, facts);
      const copy = structuredClone(facts);
      return exclusive(async () => {
        if (
          hasFsm(binding) &&
          JSON.stringify(protectedInputs(copy)) !== JSON.stringify(protectedInputs(inputs))
        )
          throw new Error("FSM state and machine are runtime-owned after registration.");
        inputs = checked(copy);
      });
    },
    check(intent: ActionIntent) {
      idle();
      return decide(binding, bundle.hash, rules, inputs, intent);
    },
    whatIf(intent: ActionIntent, hypotheticalInputs: PolicyFact[]) {
      idle();
      return decide(binding, bundle.hash, rules, checked(hypotheticalInputs), intent);
    },
    query(source: string) {
      idle();
      const parsed = parseProgram(source);
      if (parsed.facts.length || parsed.rules.length !== 1 || parsed.rules[0]!.id !== "query")
        throw new Error(
          "Session queries must be read-only query statements, without facts or rules.",
        );
      for (const atom of parsed.rules[0]!.body) {
        const schema = Object.hasOwn(binding.predicates, atom.predicate)
          ? binding.predicates[atom.predicate]
          : undefined;
        if (!schema || schema.args.length !== atom.args.length)
          throw new Error("Unknown query predicate or wrong arity.");
      }
      const combined = [...structuredClone(rules), ...parsed.rules];
      validateAndStratify([], combined);
      const result = evaluate(inputs, combined);
      return {
        columns: parsed.columns,
        rows: result.facts
          .filter((fact) => fact.predicate === "QueryResult")
          .map((fact) => fact.args.map(decode)),
      };
    },
    why(fact: PolicyFact) {
      idle();
      const encoded = encodeFact(fact);
      const result = evaluate(inputs, rules);
      return result.facts.some((item) => factKey(item) === factKey(encoded))
        ? explain(result, encoded)
        : null;
    },
    execute<T>(intent: ActionIntent, effect: () => Promise<T>, commitInputs: PolicyFact[] = []) {
      return execute(
        intent,
        { effect: async () => ({ status: "applied", value: await effect() }) },
        commitInputs,
      );
    },
    executeObserved<T>(intent: ActionIntent, options: ObservedExecution<T>) {
      return execute(intent, options);
    },
  };
}

function transitionInputs(
  inputs: PolicyFact[],
  transition: { resource: string; from: string; to: string },
  observations: PolicyFact[],
) {
  if (
    !inputs.some(
      (f) =>
        f.predicate === "ResourceState" &&
        f.args[0] === transition.resource &&
        f.args[1] === transition.from,
    )
  )
    throw new Error("Resource changed before the protected transition could commit.");
  return [
    ...inputs.filter(
      (f) => !(f.predicate === "ResourceState" && f.args[0] === transition.resource),
    ),
    ...observations,
    { predicate: "ResourceState", args: [transition.resource, transition.to] },
  ];
}
