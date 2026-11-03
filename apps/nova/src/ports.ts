import type { MessagingProfile } from "@rakazo/policy-runtime/messaging";
import { createMessagingProfile } from "@rakazo/policy-runtime/messaging";
import { PRIMITIVE_NAMES, renameFact, renameRule } from "@rakazo/policy-runtime/primitives";
import { CONFIG } from "./config.js";
import { NOVA_PREDICATES, NOVA_RULES } from "./policy.js";
import { PRINCIPALS } from "./shared.js";
import type { NovaPolicyArtifact } from "./translated-policy.js";
import { readPolicyArtifact, rulesFor } from "./translated-policy.js";

/** Application composition only: either rule origin targets the same backend-neutral primitives. */
export function novaMessagingProfile(policy?: NovaPolicyArtifact): MessagingProfile {
  const validated = policy ? readPolicyArtifact(policy) : undefined;
  const rules = validated
    ? rulesFor({ policy: validated }).filter((r) => r.id.startsWith("translated-"))
    : NOVA_RULES;
  return createMessagingProfile({
    principals: [...PRINCIPALS],
    sourceAuthorities: ["board"],
    configuration: CONFIG.map((fact) => renameFact(fact, PRIMITIVE_NAMES)),
    application: {
      predicates: NOVA_PREDICATES,
      rules: rules.map((rule) => renameRule(rule, PRIMITIVE_NAMES)),
      ruleEncoding: validated ? "parsed" : "raw",
      local: { Covered: ["_"] },
      replicated: ["Auditor", "AuditGoal"],
      observer: ["Finished"],
    },
  });
}
