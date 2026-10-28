import { createHash, randomUUID } from "node:crypto";
import type { ActionIntent, RuntimeBinding } from "./binding.js";
import { readRuntimeBinding, validateInputs, validateIntent } from "./binding.js";
import type { PolicyFact, Rule } from "./datalog.js";
import { evaluateDatalog, factKey } from "./datalog.js";
import { decode, encodeFact, limits, parseProgram, validateAndStratify } from "./query.js";

export type PolicyBundle = { version: 1; binding: RuntimeBinding; source: string; hash: string };
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
};

function parsePolicy(binding: RuntimeBinding, source: string) {
  const parsed = parseProgram(`${source}\n?- RuntimeSentinel().`);
  if (parsed.facts.length) throw new Error("Policies must contain rules, not ground facts.");
  // The source may not contain its own query, including queries after the sentinel.
  if (parsed.rules.filter((rule) => rule.id === "query").length !== 1)
    throw new Error("Policies must not contain queries.");
  const rules = parsed.rules.filter((rule) => rule.id !== "query");
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
  }
  validateAndStratify([], rules);
  return rules;
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
): ActionDecision {
  validateIntent(intent);
  const request = { ...intent, id: randomUUID() };
  const result = evaluate(
    [
      ...inputs,
      {
        predicate: binding.decision.request,
        args: [request.id, request.actor, request.action, request.resource],
      },
    ],
    rules,
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
    .update(canonical({ version: 1, binding, source }))
    .digest("hex");
  for (const test of binding.tests) {
    const decision = decide(binding, hash, rules, test.inputs, test.request);
    if (decision.allowed !== test.allowed) throw new Error(`Acceptance case failed: ${test.name}`);
  }
  return { version: 1, binding, source, hash };
}

/** In-process trusted-adapter boundary; callers never hand a decision token back to execute. */
export function createPolicySession(
  bindingInput: unknown,
  bundleInput: PolicyBundle,
  initialInputs: PolicyFact[] = [],
) {
  if (bundleInput.version !== 1) throw new Error("Unsupported policy bundle version.");
  const bundle = compileApplicationPolicy(bindingInput, bundleInput.source);
  if (bundle.hash !== bundleInput.hash) throw new Error("Policy bundle hash mismatch.");
  if (canonical(bundle.binding) !== canonical(bundleInput.binding))
    throw new Error("Policy bundle binding mismatch.");
  const binding = bundle.binding;
  const rules = parsePolicy(binding, bundle.source);
  let inputs: PolicyFact[] = [];
  let pending = 0;
  let queue: Promise<unknown> = Promise.resolve();
  const checked = (facts: PolicyFact[]) => {
    validateInputs(binding, facts);
    const copy = structuredClone(facts);
    evaluate(copy, rules); // Reject resource-limit failures before changing state or running an effect.
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
    execute<T>(
      intent: ActionIntent,
      effect: () => Promise<T>,
      commitInputs: PolicyFact[] = [],
    ): Promise<
      | { allowed: false; decision: ActionDecision }
      | { allowed: true; decision: ActionDecision; value: T }
    > {
      validateIntent(intent);
      validateInputs(binding, commitInputs);
      const captured = structuredClone({ intent, commitInputs });
      return exclusive(async () => {
        const decision = decide(binding, bundle.hash, rules, inputs, captured.intent);
        if (!decision.allowed) return { allowed: false as const, decision };
        const next = checked([...inputs, ...captured.commitInputs]);
        const value = await effect();
        inputs = next; // A failed effect never commits observations. External effects need app-owned transactions.
        return { allowed: true as const, decision, value };
      });
    },
  };
}
