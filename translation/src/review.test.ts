import { fileURLToPath } from "node:url";
import { expect, it, vi } from "vitest";
import { extractPolicies } from "./application.js";
import { policyPlanHash } from "./policy-plan.js";
import {
  buildBackTranslationPrompt,
  loadReviewApplication,
  readBackTranslation,
  readReviewPlan,
  referenceReview,
  translateForReview,
} from "./review.js";

const directory = fileURLToPath(new URL("../../apps/labcluster-port", import.meta.url));
const setup = () => loadReviewApplication(directory);

it("loads a pinned offline reference with every requirement represented, gaps and shared mappings", async () => {
  const app = await setup();
  const review = referenceReview(app);
  expect(review.origin).toBe("reference");
  expect(review.validation).toBe("static-only");
  expect(review.id).toBe(referenceReview(app).id);
  for (const requirement of review.requirements)
    expect(review.behaviors.some((b) => b.requirementIds.includes(requirement.id))).toBe(true);
  expect(review.behaviors.filter((b) => b.kind === "gap")).toHaveLength(4);
  expect(review.behaviors.find((b) => b.id === "quotas")!.requirementIds).toEqual(
    expect.arrayContaining(["P1.4", "P1.5"]),
  );
  const completion = review.behaviors.find((b) => b.id === "completion")!;
  expect(completion.evidence).toContainEqual({
    name: "ExitSuccess",
    meaning: "Zero exit code on a stored completion receipt.",
  });
  // Dependencies through the provenance foundation are also included.
  expect(completion.evidence.some((e) => e.name === "Source")).toBe(true);
});

it("back-translates only the actual program, configuration and meanings, never the original wording", async () => {
  const app = await setup();
  const prompt = JSON.parse(buildBackTranslationPrompt(app.rules, app.binding));
  expect(prompt.rules).toEqual(app.rules);
  expect(prompt.configuration).toEqual(app.binding.configuration);
  expect(prompt).not.toHaveProperty("requirements");
  expect(prompt).not.toHaveProperty("policies");
  expect(prompt).not.toHaveProperty("documents");
  expect(prompt).not.toHaveProperty("tests");
  expect(prompt.gate.semantics).toContain("no allowance means refusal");
});

it("runs distinct distillation, candidate translation and back-translation calls without approving or installing", async () => {
  const app = await setup();
  const original = structuredClone(app);
  const generate = vi
    .fn<(prompt: string) => Promise<string>>()
    .mockResolvedValueOnce(JSON.stringify(app.plan))
    .mockResolvedValueOnce(JSON.stringify({ rules: app.rules, coverage: app.coverage }))
    .mockResolvedValueOnce(JSON.stringify({ behaviors: app.readings }));
  const review = await translateForReview(
    app,
    app.documents.find((d) => d.path === "policy.md")!.content,
    generate,
  );
  expect(generate).toHaveBeenCalledTimes(3);
  expect(generate.mock.calls[1]![0]).toContain("unreviewed candidate");
  expect(generate.mock.calls[1]![0]).not.toContain("approved Datalog targets");
  expect(JSON.parse(generate.mock.calls[2]![0]).rules).toEqual(app.rules);
  expect(review.origin).toBe("model");
  expect(review).not.toHaveProperty("bundle");
  expect(review).not.toHaveProperty("approvedRequirements");
  expect(app).toEqual(original);
});

it("retains unsupported edited requirements and skips rule generation when none can be mapped", async () => {
  const app = await setup();
  const source = "P1. Never reveal any secret through any channel.";
  const documents = app.documents.map((d) =>
    d.path === "policy.md" ? { ...d, content: source } : d,
  );
  const policies = extractPolicies(source);
  const plan = {
    ...app.plan,
    sourceHash: policyPlanHash(policies),
    documentsHash: policyPlanHash(documents),
    requirements: [
      {
        id: "P1.1",
        policyId: "P1",
        start: 0,
        end: policies[0]!.text.length,
        statement: policies[0]!.text,
        implementation: "unsupported",
        relation: "unresolved",
        assumptions: ["No complete channel instrumentation is installed."],
        predicates: [],
      },
    ],
  };
  const generate = vi.fn(async () => JSON.stringify(plan));
  const review = await translateForReview(app, source, generate);
  expect(generate).toHaveBeenCalledTimes(1);
  expect(review.rules).toEqual([]);
  expect(review.behaviors[0]).toMatchObject({ kind: "gap", summary: policies[0]!.text });
  expect(review.id).not.toBe(referenceReview(app).id);
});

it("rejects stale plans, invalid programs and missing back-translation coverage", async () => {
  const app = await setup();
  const text = app.documents.find((d) => d.path === "policy.md")!.content;
  await expect(
    translateForReview(app, `${text} Changed.`, async () => JSON.stringify(app.plan)),
  ).rejects.toThrow();
  const invalid = {
    rules: app.rules.map((r, index) =>
      index ? r : { ...r, datalog: 'Job("forged", "owner", 1, "hash", "run") :- Student(A).' },
    ),
    coverage: app.coverage,
  };
  const generate = vi
    .fn<(prompt: string) => Promise<string>>()
    .mockResolvedValueOnce(JSON.stringify(app.plan))
    .mockResolvedValueOnce(JSON.stringify(invalid));
  await expect(translateForReview(app, text, generate)).rejects.toThrow();
  expect(generate).toHaveBeenCalledTimes(3);
  expect(() => readBackTranslation({ behaviors: app.readings.slice(1) }, app.rules)).toThrow(
    "omitted",
  );
  expect(() =>
    readBackTranslation({ behaviors: [{ ...app.readings[0], ruleIds: ["invented"] }] }, app.rules),
  ).toThrow("reference");
  expect(() =>
    readBackTranslation({ behaviors: [app.readings[0], app.readings[0]] }, app.rules),
  ).toThrow();
});

it("keeps unquoted source text as an explicit omission without claiming it is unsupported by the framework", async () => {
  const app = await setup();
  const plan = { ...app.plan, requirements: app.plan.requirements.filter((r) => r.id !== "P6.7") };
  const result = readReviewPlan(
    plan,
    extractPolicies(app.documents.find((d) => d.path === "policy.md")!.content),
    app.binding,
    app.documents,
  );
  expect(result.omittedRequirementIds).toEqual(["P6.7"]);
  const gap = result.plan.requirements.find((r) => r.id === "P6.7")!;
  expect(gap.statement).toBe("Role permissions are defined in P1.");
  expect(gap.relation).toBe("unresolved");
  expect(gap.assumptions[0]).toContain("has not been assessed");
  expect(plan.requirements).toHaveLength(app.plan.requirements.length - 1);
});

it("makes one recorded schema correction while keeping developer approval separate", async () => {
  const app = await setup();
  const invalid = structuredClone(app.plan);
  Object.assign(invalid.requirements[0]!, { implementation: "fsm" });
  const generate = vi
    .fn<(prompt: string) => Promise<string>>()
    .mockResolvedValueOnce(JSON.stringify(invalid))
    .mockResolvedValueOnce(JSON.stringify(app.plan))
    .mockResolvedValueOnce(JSON.stringify({ rules: app.rules, coverage: app.coverage }))
    .mockResolvedValueOnce(JSON.stringify({ behaviors: app.readings }));
  const result = await translateForReview(
    app,
    app.documents.find((d) => d.path === "policy.md")!.content,
    generate,
  );
  expect(generate).toHaveBeenCalledTimes(4);
  expect(generate.mock.calls[1]![0]).toContain("validator feedback");
  expect(result.generationAttempts.map((a) => [a.stage, a.attempt])).toEqual([
    ["distillation", 1],
    ["distillation", 2],
    ["rules", 1],
    ["backtranslation", 1],
  ]);
  expect(result.generationAttempts[0]!.validationError).toContain("implementation=fsm");
  expect(result).not.toHaveProperty("approvedRequirements");
});
