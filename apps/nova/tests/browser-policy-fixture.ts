// Synthetic UI fixture generated from the reference, never a model experiment.
import { novaDocuments } from "../src/documents.js";
import { NOVA_RULES } from "../src/policy.js";
import { createPolicyArtifact, ruleSource } from "../src/translated-policy.js";

console.log(
  JSON.stringify(
    createPolicyArtifact(
      novaDocuments(),
      [
        { id: "P1", basis: "builtin", datalog: "", notes: "Fixed lineage" },
        { id: "P2", basis: "builtin", datalog: "", notes: "Fixed capability" },
        {
          id: "P3",
          basis: "extension",
          datalog: ruleSource(NOVA_RULES.filter((rule) => rule.id.startsWith("three-tag"))),
          notes: "Synthetic browser fixture",
        },
        { id: "P4", basis: "builtin", datalog: "", notes: "Fixed gate" },
        {
          id: "P5",
          basis: "extension",
          datalog: ruleSource(NOVA_RULES.filter((rule) => !rule.id.startsWith("three-tag"))),
          notes: "Synthetic browser fixture",
        },
      ],
      "offline browser fixture",
    ),
  ),
);
