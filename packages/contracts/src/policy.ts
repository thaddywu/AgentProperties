import * as z from "zod";

export const PolicyPrincipal = z.enum(["board", "procurement", "facility", "hiring", "auditor_a"]);
export type PolicyPrincipal = z.infer<typeof PolicyPrincipal>;
export const PolicyFact = z.object({ predicate: z.string(), args: z.array(z.string()) });
export type PolicyFact = z.infer<typeof PolicyFact>;
export const PolicyLabel = z.object({ project: z.string(), component: z.string() });
export type PolicyLabel = z.infer<typeof PolicyLabel>;
export const PolicyArtifact = z.object({
  id: z.string(),
  producer: PolicyPrincipal,
  text: z.string(),
  carries: z.array(PolicyLabel),
  inputs: z.array(z.string()),
});
export type PolicyArtifact = z.infer<typeof PolicyArtifact>;
export const PolicyLocalStore = z.object({
  artifacts: z.array(z.string()),
  facts: z.array(PolicyFact),
});
export type PolicyLocalStore = z.infer<typeof PolicyLocalStore>;
export const PolicyStores = z.record(PolicyPrincipal, PolicyLocalStore);
export type PolicyStores = z.infer<typeof PolicyStores>;
export const PolicyEvent = z.object({
  seq: z.number().int(),
  kind: z.enum(["create", "compute", "send", "receive", "notice"]),
  actor: PolicyPrincipal,
  artifactId: z.string(),
  messageId: z.string().optional(),
  from: PolicyPrincipal.optional(),
  to: PolicyPrincipal.optional(),
  before: PolicyStores,
  after: PolicyStores,
  incoming: z.array(PolicyFact).default([]),
  decision: z.enum(["allow", "deny"]).optional(),
  rules: z.array(z.string()).default([]),
  witnesses: z.array(PolicyFact).default([]),
  model: z.string().optional(),
});
export type PolicyEvent = z.infer<typeof PolicyEvent>;
export const PolicyState = z.object({
  version: z.literal(1),
  phase: z.number().int(),
  status: z.enum(["ready", "blocked", "completed"]),
  artifacts: z.record(z.string(), PolicyArtifact),
  local: PolicyStores,
  events: z.array(PolicyEvent),
  counters: z.record(z.string(), z.number().int()),
});
export type PolicyState = z.infer<typeof PolicyState>;
export const PolicySession = z.object({
  id: z.string(),
  revision: z.number().int(),
  state: PolicyState,
});
export type PolicySession = z.infer<typeof PolicySession>;
