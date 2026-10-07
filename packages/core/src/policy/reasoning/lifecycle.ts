import type { PolicyFact } from "@rakazo/contracts";
import type { Rule } from "../datalog.js";
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
};
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
];
export const LIFECYCLE_RULE_TEXT = souffleProgram([], LIFECYCLE_RULES);
export function evaluateLifecycle(inputs: PolicyFact[]) {
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
  return runSouffle(inputs, LIFECYCLE_RULES);
}
