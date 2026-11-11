import catalog from "../python/policy_runtime/foundations.json" with { type: "json" };
import type { PolicyFact, Rule } from "./datalog.js";
import { runSouffle, souffleProgram } from "./souffle.js";

export const LIFECYCLE_PREDICATES = catalog.fsm.predicates as {
  [K in keyof typeof catalog.fsm.predicates]: {
    kind: "input" | "derived";
    args: string[];
    meaning: string;
  };
};
export const LIFECYCLE_INPUT_ARITIES: Record<string, number> = {
  ResourceType: 2,
  ResourceState: 2,
  InitialState: 2,
  AllowedTransition: 4,
};
export const LIFECYCLE_RULES = catalog.fsm.rules as Rule[];
export const LIFECYCLE_RULE_TEXT = souffleProgram([], LIFECYCLE_RULES);
export function validateLifecycleInputs(inputs: PolicyFact[], protectedEvents?: readonly string[]) {
  const states = new Map<string, string>(),
    types = new Map<string, string>(),
    transitions = new Map<string, string>(),
    initials = new Map<string, string>();
  for (const fact of inputs) {
    if (LIFECYCLE_INPUT_ARITIES[fact.predicate] !== fact.args.length)
      throw new Error(`Invalid lifecycle input: ${fact.predicate}`);
    if (fact.predicate === "ResourceState" || fact.predicate === "ResourceType") {
      const map = fact.predicate === "ResourceState" ? states : types;
      if (map.has(fact.args[0]!) && map.get(fact.args[0]!) !== fact.args[1])
        throw new Error(`Conflicting ${fact.predicate}`);
      map.set(fact.args[0]!, fact.args[1]!);
    }
    if (fact.predicate === "AllowedTransition") {
      if (protectedEvents && !protectedEvents.includes(fact.args[1]!))
        throw new Error("FSM selection must include every transition event.");
      const key = JSON.stringify(fact.args.slice(0, 3));
      if (transitions.has(key) && transitions.get(key) !== fact.args[3])
        throw new Error("Ambiguous transition");
      transitions.set(key, fact.args[3]!);
    }
    if (fact.predicate === "InitialState") {
      if (initials.has(fact.args[0]!) && initials.get(fact.args[0]!) !== fact.args[1])
        throw new Error("Conflicting initial state for resource type");
      initials.set(fact.args[0]!, fact.args[1]!);
    }
  }
  for (const resource of new Set([...states.keys(), ...types.keys()]))
    if (!states.has(resource) || !types.has(resource))
      throw new Error("Each resource needs one type and one current state");
}
export function evaluateLifecycle(inputs: PolicyFact[]) {
  validateLifecycleInputs(inputs);
  return runSouffle(inputs, LIFECYCLE_RULES);
}
