import { cp, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { extractPolicies, loadApplication } from "./application.js";
import { parseModelOutput, runExperiment } from "./experiment.js";
import { buildPrompt, NOVA_PREDICATES } from "./prompt.js";
import { validateDatalog } from "./validation.js";

const directories: string[] = [];
const example = resolve(import.meta.dirname, "../../apps/nova");
async function temporary() {
  const directory = await mkdtemp(join(tmpdir(), "nova-translation-test-"));
  directories.push(directory);
  return directory;
}
afterEach(async () => {
  await Promise.all(directories.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
});

describe("CS239 documents and prompt", () => {
  it("loads Nova's actual six agents and five policies without requiring episodes", async () => {
    const directory = await temporary();
    await cp(example, directory, { recursive: true });
    await rm(join(directory, "episodes"), { recursive: true });
    const documents = await loadApplication(directory);
    expect(documents.filter((doc) => doc.path.startsWith("agents/"))).toHaveLength(6);
    expect(
      extractPolicies(documents.find((doc) => doc.path === "policy.md")!.content),
    ).toHaveLength(5);
    expect(documents.find((doc) => doc.path === "tools.md")!.content.trim()).toBe("None");
  });
  it("rejects missing application documents", async () => {
    const directory = await temporary();
    await mkdir(join(directory, "agents"));
    await writeFile(join(directory, "agents", "agent.md"), "A scripted agent.");
    await expect(loadApplication(directory)).rejects.toThrow("app.md");
  });
  it("extracts complete paragraphs and rejects skipped, duplicate or unseparated policy IDs", () => {
    expect(extractPolicies("P1. A condition.\nA continuation.\n\nP2. Another condition.")).toEqual([
      { id: "P1", text: "A condition.\nA continuation." },
      { id: "P2", text: "Another condition." },
    ]);
    for (const text of ["P1. A\n\nP3. B", "P1. A\n\nP1. B", "P1. A\nP2. B"])
      expect(() => extractPolicies(text)).toThrow("consecutively");
  });
  it("includes exact documents, schema and locality without revealing reference rules", async () => {
    const documents = await loadApplication(example);
    const prompt = buildPrompt(documents);
    expect(prompt).toContain(JSON.stringify(documents, null, 2));
    expect(prompt).toContain("recipient-local");
    expect(prompt).toContain("No global cross-store joins");
    expect(prompt).not.toMatch(/DenyReceive\([^\n]*:-|REASONING_RULES|three-tag-exposure/);
    // Reference metadata may be inspected by the TEST, never by prompt construction.
    const { INPUT_ARITIES, REASONING_RULES } = await import("@rakazo/nova/policy");
    for (const [predicate, arity] of Object.entries(INPUT_ARITIES))
      expect(NOVA_PREDICATES[predicate as keyof typeof NOVA_PREDICATES].args).toHaveLength(arity);
    for (const rule of REASONING_RULES)
      expect(
        NOVA_PREDICATES[rule.head.predicate as keyof typeof NOVA_PREDICATES].args,
      ).toHaveLength(rule.head.args.length);
  });
});

describe("untrusted translation output", () => {
  const policies = [{ id: "P1", text: "Synthetic test policy." }];
  it("parses a recording wrapper and preserves the model's Datalog verbatim", () => {
    const datalog = "DenyReceive(A, M) :- Incoming(A, M).";
    const wrapper = JSON.stringify({
      policies: [{ id: "P1", datalog, notes: "Synthetic over-restrictive test output." }],
    });
    expect(parseModelOutput(`\`\`\`json\n${wrapper}\n\`\`\``, policies)[0]!.datalog).toBe(datalog);
    for (const raw of [
      "not json",
      '{"policies":[]}',
      '{"policies":[{"id":"P2","datalog":"","notes":""}]}',
    ])
      expect(() => parseModelOutput(raw, policies)).toThrow();
  });
  it.each([
    ["Imaginary(A, M) :- Incoming(A, M).", "unsupported_schema"],
    ["constructor(A, M) :- Incoming(A, M).", "unsupported_schema"],
    ["DenyReceive(A) :- Incoming(A, M).", "unsupported_schema"],
    ["HasCap(A, C) :- Requires(A, C).", "unsupported_schema"],
    ["DenyReceive(A, M) :- not Incoming(A, M).", "syntax_or_compilation_failure"],
    ['.include "private.dl"', "syntax_or_compilation_failure"],
    [
      "DenyReceive(A, M) :- Incoming(A, M), not DenyReceive(A, M).",
      "syntax_or_compilation_failure",
    ],
  ])("detects invalid output without repairing it: %s", (source, expected) => {
    expect(validateDatalog(source).status).toBe(expected);
  });
  it("checks a legal program and explicitly distinguishes missing native validation", () => {
    const result = validateDatalog("DenyReceive(A, M) :- Incoming(A, M).");
    expect(result.typescript).toBe("passed");
    expect(["valid_translation_output", "validation_blocked"]).toContain(result.status);
    expect(result.message).toMatch(/semantic correctness is unproven|requires souffle/);
  });
  it("persists partial raw response, exact inputs and failure results when the model fails", async () => {
    const root = await temporary();
    const output = join(root, "failed-run");
    const generate = vi.fn(async (_prompt, record) => {
      record('{"policies":');
      throw new Error("Synthetic model failure");
    });
    const result = await runExperiment({
      documents: await loadApplication(example),
      output,
      metadata: { model: "offline-test-only" },
      generate,
    });
    expect(generate).toHaveBeenCalledTimes(1);
    expect(result.status).toBe("model_or_parsing_failure");
    expect(await readFile(join(output, "raw-response.txt"), "utf8")).toBe('{"policies":');
    expect(await readFile(join(output, "input-documents.json"), "utf8")).toContain("policy.md");
    expect(await readFile(join(output, "report.md"), "utf8")).toContain("Synthetic model failure");
    expect(await readFile(join(output, "generated.dl"), "utf8")).toBe("");
  });
  it("saves malformed model output before attempting to parse it", async () => {
    const root = await temporary();
    const output = join(root, "malformed-run");
    const result = await runExperiment({
      documents: await loadApplication(example),
      output,
      metadata: {},
      generate: async () => "malformed response",
    });
    expect(result.status).toBe("model_or_parsing_failure");
    expect(await readFile(join(output, "raw-response.txt"), "utf8")).toBe("malformed response");
  });
});
