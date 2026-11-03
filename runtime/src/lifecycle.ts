import type { PolicyFact, Rule } from "./datalog.js";
import { runSouffle, souffleProgram } from "./souffle.js";

const f = (predicate: string, ...args: string[]): PolicyFact => ({ predicate, args });
const rule = (id: string, head: PolicyFact, body: Rule["body"]): Rule => ({
  id,
  head,
  body,
  distinct: [],
  stratum: 1,
});
/** Application-neutral state checks. No resources are added to Nova. */
export const LIFECYCLE_INPUT_ARITIES: Record<string, number> = {
  ResourceType: 2,
  ResourceState: 2,
  Transition: 4, // Type, Action, From, To: one machine definition can serve many resources.
  ActionTaken: 5, // Event, Resource, Action, From, To: immutable execution history.
  ResourceRecovery: 2, // Resource, Attempt: an external outcome requires reconciliation.
};
export const LIFECYCLE_PREDICATES = {
  ResourceType: { kind: "input", args: ["Resource", "Type"], source: "config" },
  ResourceState: { kind: "input", args: ["Resource", "State"], source: "runtime" },
  Transition: { kind: "input", args: ["Type", "Action", "From", "To"], source: "config" },
  ActionTaken: {
    kind: "input",
    args: ["Event", "Resource", "Action", "From", "To"],
    source: "runtime",
  },
  ResourceRecovery: { kind: "input", args: ["Resource", "Attempt"], source: "runtime" },
  EnabledAction: { kind: "derived", args: ["Resource", "State", "Action"], source: "inference" },
  ReachableState: { kind: "derived", args: ["Resource", "From", "To"], source: "inference" },
  KnownResource: { kind: "derived", args: ["Resource"], source: "inference" },
  CanTransition: {
    kind: "derived",
    args: ["Resource", "Action", "From", "To"],
    source: "inference",
  },
} as const;
export const LIFECYCLE_RULES: Rule[] = [
  rule("enabled-action", f("EnabledAction", "R", "From", "Action"), [
    f("ResourceType", "R", "Type"),
    f("Transition", "Type", "Action", "From", "To"),
  ]),
  rule("direct-reachability", f("ReachableState", "R", "From", "To"), [
    f("ResourceType", "R", "Type"),
    f("Transition", "Type", "Action", "From", "To"),
  ]),
  rule("transitive-reachability", f("ReachableState", "R", "From", "To"), [
    f("ReachableState", "R", "From", "Mid"),
    f("ResourceType", "R", "Type"),
    f("Transition", "Type", "Action", "Mid", "To"),
  ]),
  rule("known-resource", f("KnownResource", "R"), [
    f("ResourceType", "R", "Type"),
    f("ResourceState", "R", "State"),
  ]),
  rule("current-transition", f("CanTransition", "R", "Action", "From", "To"), [
    f("ResourceType", "R", "Type"),
    f("ResourceState", "R", "From"),
    f("Transition", "Type", "Action", "From", "To"),
  ]),
];
export const LIFECYCLE_RULE_TEXT = souffleProgram([], LIFECYCLE_RULES);
export function validateLifecycleInputs(inputs: PolicyFact[]) {
  const states = new Map<string, string>(),
    types = new Map<string, string>(),
    transitions = new Map<string, string>();
  for (const fact of inputs) {
    if (LIFECYCLE_INPUT_ARITIES[fact.predicate] !== fact.args.length)
      throw new Error(`Invalid lifecycle input: ${fact.predicate}`);
    if (fact.predicate === "ResourceState" || fact.predicate === "ResourceType") {
      const map = fact.predicate === "ResourceState" ? states : types;
      const [resource, value] = fact.args;
      if (map.has(resource!) && map.get(resource!) !== value)
        throw new Error(`Conflicting ${fact.predicate}`);
      map.set(resource!, value!);
    }
    if (fact.predicate === "Transition") {
      const key = JSON.stringify(fact.args.slice(0, 3)),
        to = fact.args[3]!;
      if (transitions.has(key) && transitions.get(key) !== to)
        throw new Error("Ambiguous transition");
      transitions.set(key, to);
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

/** Gate names come from the application's trusted binding; state legality remains builtin. */
export function lifecycleGateRules(request: string, deny: string): Rule[] {
  const intent = f(request, "Q", "Actor", "Action", "R");
  return [
    rule("unknown-resource", f(deny, "Q", "unknown_resource"), [
      intent,
      { ...f("KnownResource", "R"), negative: true },
    ]),
    rule("invalid-transition", f(deny, "Q", "invalid_transition"), [
      intent,
      f("ResourceState", "R", "From"),
      { ...f("EnabledAction", "R", "From", "Action"), negative: true },
    ]),
    rule("resource-recovery", f(deny, "Q", "recovery_required"), [
      intent,
      f("ResourceRecovery", "R", "Attempt"),
    ]),
  ];
}
