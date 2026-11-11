import { createHash } from "node:crypto";
import type { NovaPolicyArtifact } from "../translated-policy.js";
import { createPolicyArtifact, FOUNDATION_ID, readPolicyArtifact } from "../translated-policy.js";

/** Explicit offline schema migration. Saved model responses and their hashes remain unchanged. */
export function recordedPolicy(input: unknown): NovaPolicyArtifact {
  const value = input as NovaPolicyArtifact;
  if (value?.foundation === FOUNDATION_ID) return readPolicyArtifact(value);
  if (
    value?.format !== "nova-extension-v1" ||
    value.foundation !== "5476a92d4fc8ce313d1c82e3da63b15c769f71b3956799b45629072f5c44a39b"
  )
    throw new Error("Unknown recorded experiment schema.");
  const { id, ...content } = value;
  if (createHash("sha256").update(JSON.stringify(content)).digest("hex") !== id)
    throw new Error("Recorded experiment identity mismatch.");
  const policies = value.policies.map((policy) => ({
    ...policy,
    datalog: policy.datalog.replace(
      /DenyReceive\(([^,()]+),\s*([^()]+)\)/g,
      (_match, _principal, message: string) => `Deny(${message.trim()}, message_policy)`,
    ),
  }));
  return createPolicyArtifact(
    value.documents,
    policies,
    `${value.model} [explicit schema migration]`,
  );
}
