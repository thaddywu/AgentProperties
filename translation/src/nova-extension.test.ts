import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { novaDocuments } from "@rakazo/nova/documents";
import { NOVA_RULES } from "@rakazo/nova/policy";
import { ruleSource } from "@rakazo/nova/translated-policy";
import { describe, expect, it } from "vitest";
import { extensionPrompt, translateNovaExtension } from "./nova-extension.js";

describe("one-shot Nova extension translation", () => {
  it("exposes only foundation rules, fixed protocol and exact app input to generation", () => {
    const prompt = extensionPrompt(novaDocuments());
    expect(prompt).toContain("trusted-label");
    expect(prompt).toContain("TransportTag");
    expect(prompt).toContain("policy.md");
    expect(prompt).not.toContain("three-tag-exposure");
    expect(prompt).not.toContain(ruleSource(NOVA_RULES));
    expect(prompt).not.toContain("episodes/");
  });
  it("persists one generated extension, compares actual gates and exports a reloadable artifact", async () => {
    const root = mkdtempSync(join(tmpdir(), "nova-extension-test-"));
    let calls = 0;
    try {
      const result = await translateNovaExtension({
        documents: novaDocuments(),
        output: join(root, "run"),
        metadata: { model: "offline test fixture" },
        generate: async (_prompt, record) => {
          calls++;
          const output = JSON.stringify({
            policies: [
              { id: "P1", basis: "builtin", datalog: "", notes: "Fixed lineage" },
              { id: "P2", basis: "builtin", datalog: "", notes: "Fixed capability" },
              {
                id: "P3",
                basis: "extension",
                datalog: ruleSource(NOVA_RULES.filter((r) => r.id.startsWith("three-tag"))),
                notes: "Synthetic reference fixture",
              },
              { id: "P4", basis: "builtin", datalog: "", notes: "Fixed protocol" },
              {
                id: "P5",
                basis: "extension",
                datalog: ruleSource(NOVA_RULES.filter((r) => !r.id.startsWith("three-tag"))),
                notes: "Synthetic reference fixture",
              },
            ],
          });
          record(output);
          return output;
        },
      });
      expect(calls).toBe(1);
      expect(result.status).toBe("validated_nova_extension");
      const artifact = JSON.parse(readFileSync(join(root, "run", "nova-policy.json"), "utf8"));
      expect(artifact.format).toBe("nova-extension-v1");
      expect(artifact.policies[2].basis).toBe("extension");
      expect(result.protocolGenerated).toBe(false);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
