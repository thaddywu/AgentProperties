import type { FiniteComparison, InputLiteral } from "@rakazo/policy-runtime/finite-domain";
import { encodeRule } from "@rakazo/policy-runtime/query";
import { f, PREDICATES } from "../policy.js";
import type { NovaPolicyArtifact } from "../translated-policy.js";
import { rulesFor } from "../translated-policy.js";
import { NOVA_TAGS } from "./oracle.js";

/** Explicit finite EDB catalog; declarations here do not grant an agent fact-writing authority. */
export function novaComparison(
  policy: NovaPolicyArtifact,
  options: {
    grouping: "fixed" | "variable";
    noPriorExposure: boolean;
    observables: string[];
  },
): FiniteComparison {
  const prior = NOVA_TAGS.map((tag) => f("TransportTag", "m0", tag));
  const hiringGroup = f("TagGroup", "nova_hiring", "nova");
  const noExposure: InputLiteral[] = prior.map((fact) => ({ fact, present: false }));
  if (options.grouping === "variable") noExposure.push({ fact: hiringGroup, present: false });
  return {
    schema: PREDICATES,
    reference: rulesFor({}).map(encodeRule),
    translated: rulesFor({ policy }),
    observables: options.observables,
    space: {
      required: [
        f("Incoming", "auditor_a", "m3"),
        f("Auditor", "auditor_a"),
        f("AuditGoal", "nova", ...NOVA_TAGS),
        f("Requires", "nova_hiring", "hr_review"),
        ...[0, 1, 2].map((i) => f("Received", "auditor_a", `m${i}`)),
        ...[1, 2, 3].map((i) => f("Sender", "auditor_a", `m${i}`)),
        ...NOVA_TAGS.slice(0, 2).map((tag) => f("TagGroup", tag, "nova")),
        ...(options.grouping === "fixed" ? [hiringGroup] : []),
      ],
      optional: [
        ...prior,
        ...NOVA_TAGS.map((tag) => f("TransportTag", "m3", tag)),
        ...[
          [0, 1],
          [1, 2],
          [2, 3],
          [0, 2],
          [1, 3],
          [2, 1],
        ].map(([a, b]) => f("ReceivedBeforeSend", `m${a}`, `m${b}`)),
        f("HasCap", "auditor_a", "hr_review"),
        ...(options.grouping === "variable" ? [hiringGroup] : []),
      ],
      constraints: options.noPriorExposure ? [noExposure] : [],
    },
  };
}
