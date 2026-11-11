import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { PolicyBundle } from "@rakazo/policy-runtime/application";
import { readRuntimeBinding } from "@rakazo/policy-runtime/binding";
import { CAPABILITY_PREDICATES } from "@rakazo/policy-runtime/foundations";
import { afterEach, expect, it, vi } from "vitest";
import { createDocumentService } from "../../apps/document-vault/src/service.js";
import { extractPolicies, loadApplication } from "./application.js";
import { buildApplicationPrompt, translateApplication } from "./application-translation.js";
import { policyPlanHash } from "./policy-plan.js";

const roots: string[] = [];
afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});
async function setup() {
  const root = await mkdtemp(join(tmpdir(), "application-translation-"));
  roots.push(root);
  const app = new URL("../../apps/document-vault/", import.meta.url);
  const documents = await loadApplication(app.pathname);
  const trustedBinding = readRuntimeBinding(
    JSON.parse(await readFile(new URL("runtime.json", app), "utf8")),
  );
  const originals = extractPolicies(documents.find((d) => d.path === "policy.md")!.content);
  const plan = {
    version: 1,
    sourceHash: policyPlanHash(originals),
    bindingHash: policyPlanHash(trustedBinding),
    documentsHash: policyPlanHash(documents),
    requirements: originals.map((p) => ({
      id: `${p.id}.1`,
      policyId: p.id,
      start: 0,
      end: p.text.length,
      statement: p.id === "P3" ? `${p.text.split(". ")[0]}.` : p.text,
      implementation: "datalog",
      relation: "equivalent",
      assumptions: [],
      predicates: [],
    })),
  };
  plan.requirements.push({
    id: "P3.2",
    policyId: "P3",
    start: 0,
    end: originals[2]!.text.length,
    statement:
      "Commit successful-read observations only after the service callback succeeds; denied requests release no content.",
    implementation: "adapter",
    relation: "equivalent",
    assumptions: [],
    predicates: [],
  });
  const review = {
    version: 1,
    planHash: policyPlanHash(plan),
    approvedRequirements: plan.requirements.map((r) => r.id),
    obligations: {
      "P3.2":
        "The service integration test checks callback count, returned bodies and successful-read observations.",
    },
    acknowledgedGaps: [] as string[],
  };
  return {
    output: join(root, "run"),
    plan,
    review,
    documents,
    binding: trustedBinding,
  };
}
const policies = [
  {
    id: "P1.1",
    datalog: 'Allow(R) :- Request(R, A, "read"), Parameter(R, "resource", D), Accessible(A, D).',
    notes: "Synthetic offline model output.",
  },
  {
    id: "P2.1",
    datalog: 'Deny(R, "suspended") :- Request(R, A, X), Parameter(R, "resource", D), Suspended(A).',
    notes: "",
  },
  {
    id: "P3.1",
    datalog:
      'Accessible(A, D) :- Actor(A), Public(D), not Suspended(A).\nAccessible(A, D) :- Actor(A), Confidential(D), Reader(A, D), Role(A, "reviewer"), not Suspended(A).',
    notes: "Successful-read instrumentation remains the app's responsibility.",
  },
];

it("exposes installed mechanism semantics without leaking independent acceptance cases", async () => {
  const options = await setup();
  options.binding.mechanisms = ["capability"];
  Object.assign(options.binding.predicates, CAPABILITY_PREDICATES);
  const prompt = buildApplicationPrompt(options.documents, options.binding);
  expect(prompt).toContain('"capability"');
  expect(prompt).toContain('"Can"');
  expect(prompt).toContain('"ResourceGroup"');
  expect(prompt).toContain('"immutablePredicates"');
  expect(prompt).toContain('"foundationRules"');
  expect(prompt).not.toContain('"tests"');
  expect(prompt).not.toContain("public-read");
});

it("runs app documents -> one translation -> validated artifact -> real gated app -> query and why", async () => {
  const options = await setup();
  const generate = vi.fn(async (prompt: string) => {
    expect(prompt).not.toContain("Nova");
    expect(prompt).not.toContain("public-read"); // Held-out binding acceptance cases are not prompt examples.
    expect(prompt).not.toContain('"tests"');
    return JSON.stringify({
      rules: policies.map((p, i) => ({ id: `r${i}`, datalog: p.datalog })),
      coverage: policies.map((p, i) => ({ id: p.id, ruleIds: [`r${i}`], notes: p.notes })),
    });
  });
  const result = await translateApplication({ ...options, generate });
  expect(result.status).toBe("validated_policy_bundle");
  expect(generate).toHaveBeenCalledTimes(1);
  const artifact = JSON.parse(
    await readFile(join(options.output, "policy-bundle.json"), "utf8"),
  ) as PolicyBundle;
  const service = createDocumentService(
    options.binding,
    artifact,
    [
      { predicate: "Actor", args: ["visitor"] },
      { predicate: "Public", args: ["guide"] },
      { predicate: "Confidential", args: ["draft"] },
    ],
    { guide: "guide body", draft: "synthetic secret body" },
  );
  const denied = await service.read("visitor", "draft");
  expect(denied.allowed).toBe(false);
  expect(denied).not.toHaveProperty("value");
  expect(service.payloadReads).toBe(0);
  expect((await service.read("visitor", "guide")).allowed).toBe(true);
  expect(service.payloadReads).toBe(1);
  expect(service.session.query("?- Read(A, D).").rows).toEqual([["visitor", "guide"]]);
  expect(
    service.session.why({ predicate: "Accessible", args: ["visitor", "guide"] })?.rule,
  ).toBeTruthy();
});

it("does not emit an executable artifact for weakened or incomplete policies; raw output survives", async () => {
  for (const outputPolicies of [
    policies.map((policy) => ({
      ...policy,
      datalog: policy.datalog.replace(', Role(A, "reviewer")', ""),
    })),
    policies.map((policy) => ({ ...policy, datalog: policy.id === "P2.1" ? "" : policy.datalog })),
  ]) {
    const options = await setup();
    const raw = JSON.stringify({
      rules: outputPolicies.map((p, i) => ({ id: `r${i}`, datalog: p.datalog })),
      coverage: outputPolicies.map((p, i) => ({ id: p.id, ruleIds: [`r${i}`], notes: p.notes })),
    });
    const result = await translateApplication({ ...options, generate: async () => raw });
    expect(result.status).not.toBe("validated_policy_bundle");
    await expect(readFile(join(options.output, "policy-bundle.json"))).rejects.toThrow();
    expect(await readFile(join(options.output, "raw-response.txt"), "utf8")).toBe(raw);
  }
});

it("shares one generated rule across requirements instead of forcing duplicate rules", async () => {
  const options = await setup();
  options.plan.requirements.push({ ...options.plan.requirements[0]!, id: "P1.2" });
  options.review.planHash = policyPlanHash(options.plan);
  options.review.approvedRequirements.push("P1.2");
  const raw = {
    rules: policies.map((p, i) => ({ id: `r${i}`, datalog: p.datalog })),
    coverage: [
      ...policies.map((p, i) => ({ id: p.id, ruleIds: [`r${i}`], notes: p.notes })),
      { id: "P1.2", ruleIds: ["r0"], notes: "Shared authorization rule." },
    ],
  };
  const result = await translateApplication({
    ...options,
    generate: async () => JSON.stringify(raw),
  });
  expect(result.status).toBe("validated_policy_bundle");
  expect(
    (await readFile(join(options.output, "generated.dl"), "utf8")).split(policies[0]!.datalog)
      .length - 1,
  ).toBe(1);
});

it("retains acknowledged unsupported requirements without asking for fabricated rules", async () => {
  const options = await setup();
  const obligation = options.plan.requirements.find((r) => r.id === "P3.2")!;
  obligation.implementation = "unsupported";
  obligation.relation = "partial";
  options.review.planHash = policyPlanHash(options.plan);
  options.review.acknowledgedGaps.push("P3.2");
  const result = await translateApplication({
    ...options,
    generate: async () =>
      JSON.stringify({
        rules: policies.map((p, i) => ({ id: `r${i}`, datalog: p.datalog })),
        coverage: policies.map((p, i) => ({ id: p.id, ruleIds: [`r${i}`], notes: p.notes })),
      }),
  });
  expect(result.status).toBe("validated_partial_policy_bundle");
  const coverage = JSON.parse(await readFile(join(options.output, "coverage.json"), "utf8"));
  expect(coverage.acknowledgedGaps).toEqual(["P3.2"]);
  expect(coverage.requirements.find((r: { id: string }) => r.id === "P3.2").datalog).toBeNull();
});

it.each(["labcluster-port", "scam-port"])(
  "validates %s reviewed reference artifacts without a model call",
  async (name) => {
    const options = await setup();
    const app = new URL(`../../apps/${name}/`, import.meta.url);
    const load = async (name: string) =>
      JSON.parse(await readFile(new URL(`generated/${name}`, app), "utf8"));
    const result = await translateApplication({
      output: options.output,
      documents: await loadApplication(app.pathname),
      binding: await load("runtime.json"),
      plan: await load("policy-plan.json"),
      review: await load("policy-review.json"),
      metadata: { generation: "Developer-authored reference fixture; no model called." },
      generate: async () => JSON.stringify(await load("reference-output.json")),
    });
    expect(result.status).toBe("validated_partial_policy_bundle");
  },
);
