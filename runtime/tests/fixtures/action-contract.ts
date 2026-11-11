import type { RuntimeBinding } from "../../src/binding.js";
import type { PolicyFact } from "../../src/datalog.js";

const f = (predicate: string, ...args: string[]): PolicyFact => ({ predicate, args });
export const binding: RuntimeBinding = {
  version: 1,
  id: "generic-action-port",
  context: "Fictional resource service with version-bound operations.",
  predicates: {
    Request: {
      kind: "input",
      args: ["Request", "Actor", "Action"],
      meaning: "Runtime intent.",
    },
    Parameter: {
      kind: "input",
      args: ["Request", "Name", "Value"],
      meaning: "Runtime-bound parameters.",
    },
    Grant: { kind: "input", args: ["Actor", "Resource"], meaning: "Authoritative grant." },
    Version: {
      kind: "input",
      args: ["Resource", "Version"],
      meaning: "Authoritative resource version.",
    },
    Done: { kind: "input", args: ["Request", "Receipt"], meaning: "Actual committed receipt." },
    Allow: { kind: "derived", args: ["Request"], meaning: "Explicit authorization." },
    Deny: { kind: "derived", args: ["Request", "Reason"], meaning: "Mandatory refusal." },
  },
  decision: { request: "Request", allow: "Allow", deny: "Deny", parameters: "Parameter" },
  tests: [
    {
      name: "matching-version",
      inputs: [f("Grant", "operator", "item"), f("Version", "item", "v1")],
      request: {
        actor: "operator",
        action: "apply",
        resource: "item",
        parameters: { version: "v1" },
      },
      allowed: true,
    },
    {
      name: "stale-version",
      inputs: [f("Grant", "operator", "item"), f("Version", "item", "v2")],
      request: {
        actor: "operator",
        action: "apply",
        resource: "item",
        parameters: { version: "v1" },
      },
      allowed: false,
    },
  ],
};
export const policy =
  'Allow(Q) :- Request(Q, A, "apply"), Parameter(Q, "resource", R), Grant(A, R), Parameter(Q, "version", V), Version(R, V).';
