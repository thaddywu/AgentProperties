import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { readRuntimeBinding } from "@rakazo/policy-runtime/binding";
import { expect, it, vi } from "vitest";
import { extractPolicies, loadApplication } from "./application.js";
import { translateApplication } from "./application-translation.js";
import { policyPlanHash, readPolicyPlan, reviewPolicyPlan } from "./policy-plan.js";

async function fixture() {
  const root = new URL("../../apps/document-vault/", import.meta.url);
  const documents = await loadApplication(root.pathname);
  const binding = readRuntimeBinding(
    JSON.parse(await readFile(new URL("runtime.json", root), "utf8")),
  );
  const policies = extractPolicies(documents.find((d) => d.path === "policy.md")!.content);
  const plan = {
    version: 1 as const,
    sourceHash: policyPlanHash(policies),
    bindingHash: policyPlanHash(binding),
    documentsHash: policyPlanHash(documents),
    requirements: policies.map((p) => ({
      id: `${p.id}.1`,
      policyId: p.id,
      start: 0,
      end: p.text.length,
      statement: p.text,
      implementation: "datalog" as const,
      relation: "equivalent" as const,
      assumptions: [],
      predicates: [],
    })),
  };
  return { documents, binding, policies, plan };
}

it("keeps distillation separate from executable installation and never accepts model approval", async () => {
  const f = await fixture();
  const root = await mkdtemp(join(tmpdir(), "policy-distill-"));
  try {
    const generate = vi.fn(async () => JSON.stringify({ ...f.plan, review: { approved: true } }));
    const result = await translateApplication({
      ...f,
      plan: undefined,
      output: join(root, "candidate"),
      generate,
    });
    expect(result.status).toBe("policy_review_required");
    expect(generate).toHaveBeenCalledTimes(1);
    await expect(readFile(join(root, "candidate", "policy-bundle.json"))).rejects.toThrow();
    expect(() => reviewPolicyPlan(f.plan, undefined)).toThrow("developer review");
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

it("rejects missing clauses, stale source hashes, undeclared observations and uninstalled builtin claims", async () => {
  const f = await fixture();
  for (const plan of [
    { ...f.plan, sourceHash: "stale" },
    { ...f.plan, documentsHash: "stale" },
    { ...f.plan, bindingHash: "stale" },
    { ...f.plan, requirements: f.plan.requirements.slice(1) },
    { ...f.plan, requirements: f.plan.requirements.map((r) => ({ ...r, end: 1 })) },
    {
      ...f.plan,
      requirements: f.plan.requirements.map((r) => ({ ...r, predicates: ["TrustMe"] })),
    },
    {
      ...f.plan,
      requirements: f.plan.requirements.map((r) => ({
        ...r,
        implementation: "mechanism",
        mechanism: "capability",
      })),
    },
  ])
    expect(() => readPolicyPlan(plan, f.policies, f.binding, f.documents)).toThrow();
});

it("computes spans from exact quotations rather than making a model count offsets", async () => {
  const f = await fixture();
  const quoted = {
    ...f.plan,
    requirements: f.plan.requirements.map((r, i) => ({
      ...r,
      start: undefined,
      end: undefined,
      source: f.policies[i]!.text,
    })),
  };
  const plan = readPolicyPlan(quoted, f.policies, f.binding, f.documents);
  expect(plan.requirements.map((r) => [r.start, r.end])).toEqual(
    f.policies.map((p) => [0, p.text.length]),
  );
  quoted.requirements[0]!.source = "invented clause";
  expect(() => readPolicyPlan(quoted, f.policies, f.binding, f.documents)).toThrow("original span");
});

it("requires pinned developer acknowledgement and verification evidence for non-rule coverage", async () => {
  const f = await fixture();
  const plan = {
    ...f.plan,
    requirements: f.plan.requirements.map((r) => ({
      ...r,
      implementation: "adapter" as const,
      relation: "partial" as const,
    })),
  };
  const base = {
    version: 1,
    planHash: policyPlanHash(plan),
    approvedRequirements: plan.requirements.map((r) => r.id),
    acknowledgedGaps: [],
    obligations: {},
  };
  expect(() => reviewPolicyPlan(plan, base)).toThrow("verification");
  const review = {
    ...base,
    obligations: Object.fromEntries(
      plan.requirements.map((r) => [
        r.id,
        "Run the independently specified backend conformance case.",
      ]),
    ),
  };
  expect(() => reviewPolicyPlan(plan, review)).toThrow("acknowledgement");
  const reviewed = reviewPolicyPlan(plan, {
    ...review,
    acknowledgedGaps: base.approvedRequirements,
  });
  expect(reviewed.partial).toBe(true);
  expect(reviewed.targets).toEqual([]);
  expect(() => reviewPolicyPlan(plan, { ...review, planHash: "stale" })).toThrow("pin");
});

it("does not call a model or fabricate rules for an entirely non-Datalog assessment", async () => {
  const f = await fixture();
  const plan = {
    ...f.plan,
    requirements: f.plan.requirements.map((r) => ({
      ...r,
      implementation: "unsupported" as const,
      relation: "unresolved" as const,
    })),
  };
  const review = {
    version: 1,
    planHash: policyPlanHash(plan),
    approvedRequirements: plan.requirements.map((r) => r.id),
    acknowledgedGaps: plan.requirements.map((r) => r.id),
    obligations: {},
  };
  const root = await mkdtemp(join(tmpdir(), "no-datalog-targets-"));
  try {
    const generate = vi.fn(async () => {
      throw new Error("No translation was needed.");
    });
    const result = await translateApplication({
      ...f,
      plan,
      review,
      output: join(root, "review"),
      generate,
    });
    expect(result.status).toBe("reviewed_without_datalog");
    expect(generate).not.toHaveBeenCalled();
    await expect(readFile(join(root, "review", "policy-bundle.json"))).rejects.toThrow();
    const coverage = JSON.parse(await readFile(join(root, "review", "coverage.json"), "utf8"));
    expect(coverage.requirements).toHaveLength(3);
    expect(coverage.partial).toBe(true);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
