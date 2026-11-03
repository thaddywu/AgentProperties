import { createHash } from "node:crypto";
import type { Rule } from "@rakazo/policy-runtime/datalog";
import { MESSAGING_RULES } from "@rakazo/policy-runtime/messaging-policy";
import { parseProgram, validateAndStratify } from "@rakazo/policy-runtime/query";
import { souffleProgram } from "@rakazo/policy-runtime/souffle";
import { PREDICATES, REASONING_RULES } from "./policy.js";
import { PROTOCOL } from "./protocol.js";

export type Document = { path: string; content: string };
export type PolicyExtension = {
  id: string;
  datalog: string;
  notes: string;
  basis: "builtin" | "extension";
};
export type NovaPolicyArtifact = {
  format: "nova-extension-v1";
  foundation: string;
  protocol: typeof PROTOCOL;
  documents: Document[];
  policies: PolicyExtension[];
  model: string;
  id: string;
};
const hash = (value: unknown) => createHash("sha256").update(JSON.stringify(value)).digest("hex");
export const FOUNDATION_ID = hash({
  rules: MESSAGING_RULES,
  protocol: PROTOCOL,
  schemas: PREDICATES,
});
export const GOLDEN_ID = hash({ rules: REASONING_RULES, protocol: PROTOCOL });
export function ruleSource(rules: Rule[]) {
  return souffleProgram([], rules)
    .split("\n")
    .filter((line) => !line.startsWith("."))
    .join("\n")
    .replace(/!(?=[A-Za-z])/g, "not ");
}
export const FOUNDATION_SOURCE = ruleSource(Object.values(MESSAGING_RULES));

/** Parse the combined program so extension/foundation dependencies share stratification. */
export function compileExtensions(policies: PolicyExtension[]): Rule[] {
  const source = policies.map((p) => p.datalog).join("\n");
  const extension = parseProgram(`${source}\n?- TranslationSentinel().`);
  if (extension.facts.length) throw new Error("Extensions cannot introduce ground facts.");
  const rules = extension.rules.filter((r) => r.id !== "query");
  if (!rules.length) throw new Error("Nova extension contains no rules.");
  for (const rule of rules) {
    if (!["DenyReceive", "Covered", "Finished"].includes(rule.head.predicate))
      throw new Error(`Extension cannot write ${rule.head.predicate}.`);
    if (
      rule.head.predicate !== "Finished" &&
      rule.body.some((atom) => atom.predicate === "Finished")
    )
      throw new Error("Observer-only Finished cannot feed local inference or enforcement.");
    for (const atom of [rule.head, ...rule.body]) {
      const schema = Object.hasOwn(PREDICATES, atom.predicate)
        ? PREDICATES[atom.predicate]
        : undefined;
      if (!schema || schema.args.length !== atom.args.length)
        throw new Error(`Unknown predicate or wrong arity: ${atom.predicate}.`);
    }
  }
  const combined = parseProgram(`${FOUNDATION_SOURCE}\n${source}\n?- TranslationSentinel().`);
  validateAndStratify(combined.facts, combined.rules);
  return combined.rules
    .filter((r) => r.id !== "query")
    .map((rule, index) => ({
      ...rule,
      id:
        index < Object.keys(MESSAGING_RULES).length
          ? Object.keys(MESSAGING_RULES)[index]!
          : `translated-${index - Object.keys(MESSAGING_RULES).length + 1}`,
    }));
}

export function createPolicyArtifact(
  documents: Document[],
  policies: PolicyExtension[],
  model: string,
): NovaPolicyArtifact {
  const value = {
    format: "nova-extension-v1" as const,
    foundation: FOUNDATION_ID,
    protocol: PROTOCOL,
    documents,
    policies,
    model,
  };
  return readPolicyArtifact({ ...value, id: hash(value) });
}
/** Untrusted file/checkpoint data is checked again; a supplied hash is not validation evidence. */
export function readPolicyArtifact(input: unknown): NovaPolicyArtifact {
  if (!input || typeof input !== "object" || JSON.stringify(input).length > 200_000)
    throw new Error("Invalid Nova artifact or artifact exceeds 200 KB.");
  const value = input as NovaPolicyArtifact;
  if (
    value.format !== "nova-extension-v1" ||
    value.foundation !== FOUNDATION_ID ||
    JSON.stringify(value.protocol) !== JSON.stringify(PROTOCOL)
  )
    throw new Error("Artifact foundation/protocol does not match this runtime.");
  if (
    typeof value.model !== "string" ||
    value.model.length > 200 ||
    !Array.isArray(value.documents) ||
    !Array.isArray(value.policies)
  )
    throw new Error("Artifact needs model, documents and policies.");
  const paths = new Set<string>();
  for (const document of value.documents) {
    if (
      !document ||
      typeof document.path !== "string" ||
      typeof document.content !== "string" ||
      !/^(app\.md|policy\.md|tools\.md|agents\/[a-zA-Z0-9_-]+\.md)$/.test(document.path) ||
      !document.content.trim() ||
      paths.has(document.path)
    )
      throw new Error("Invalid or duplicate input document.");
    paths.add(document.path);
  }
  if (
    !["app.md", "policy.md", "tools.md"].every((path) => paths.has(path)) ||
    ![...paths].some((path) => path.startsWith("agents/"))
  )
    throw new Error("Artifact is missing application documents.");
  const paragraphs = value.documents
    .find((doc) => doc.path === "policy.md")!
    .content.trim()
    .split(/\r?\n\s*\r?\n/)
    .filter((p) => !p.startsWith("#"));
  const ids = paragraphs.map((paragraph, i) => {
    if (!paragraph.startsWith(`P${i + 1}. `))
      throw new Error("Policies must be consecutive numbered paragraphs.");
    return `P${i + 1}`;
  });
  if (!ids.length || value.policies.length !== ids.length)
    throw new Error("Incomplete policy coverage.");
  for (const [i, policy] of value.policies.entries()) {
    if (
      !policy ||
      policy.id !== ids[i] ||
      typeof policy.datalog !== "string" ||
      typeof policy.notes !== "string" ||
      !["builtin", "extension"].includes(policy.basis) ||
      (policy.basis === "builtin" ? !!policy.datalog.trim() : !policy.datalog.trim())
    )
      throw new Error("Each policy needs ordered ID, notes and builtin/extension coverage.");
  }
  const { id, ...content } = value;
  if (id !== hash(content)) throw new Error("Artifact identity mismatch.");
  compileExtensions(value.policies);
  return structuredClone(value);
}
export function rulesFor(state: { policy?: NovaPolicyArtifact }): Rule[] {
  return state.policy ? compileExtensions(state.policy.policies) : REASONING_RULES;
}
