import { runSouffle } from "@rakazo/policy-runtime/souffle";
import { novaDocuments } from "../documents.js";
import { localRules } from "../local-store.js";
import { f } from "../policy.js";
import { createPolicyArtifact } from "../translated-policy.js";

/** Author-coded boundary probes, not a sample estimating real-world policy coverage. */
export function expressivenessPilot() {
  const publicSample = JSON.parse(
    readFileSync(new URL("../../evaluation/public-policy-sample.json", import.meta.url), "utf8"),
  ) as {
    source: string;
    method: string;
    items: { id: string; currentNova: string }[];
  };
  const probes = [
    {
      id: "two-part-limit",
      policy: "Reject two distinct same-group parts in one incoming message.",
      expected: true,
      source:
        'DenyReceive(P, M) :- Incoming(P, M), MessageTag(M, A), MessageTag(M, B), TagGroup(A, G), TagGroup(B, G), A != B, P != "board".',
    },
    {
      id: "four-part-limit",
      policy: "Reject four distinct same-group parts in one incoming message.",
      expected: true,
      source:
        'DenyReceive(P, M) :- Incoming(P, M), MessageTag(M, A), MessageTag(M, B), MessageTag(M, C), MessageTag(M, D), TagGroup(A, G), TagGroup(B, G), TagGroup(C, G), TagGroup(D, G), A != B, A != C, A != D, B != C, B != D, C != D, P != "board".',
    },
    {
      id: "helper-relation",
      policy: "Factor a policy through a new reusable helper relation.",
      expected: false,
      source: "NeedsReview(P, M) :- Incoming(P, M). DenyReceive(P, M) :- NeedsReview(P, M).",
    },
    {
      id: "approval-observation",
      policy: "Receive a document only after independent approval.",
      expected: false,
      source: "DenyReceive(P, M) :- Incoming(P, M), not Approved(M).",
    },
    {
      id: "deadline",
      policy: "Reject a message after its deadline.",
      expected: false,
      source: "DenyReceive(P, M) :- Incoming(P, M), Expired(M).",
    },
    {
      id: "arithmetic",
      policy: "Limit total cost to a numeric budget using arithmetic comparisons.",
      expected: false,
      source: "DenyReceive(P, M) :- Incoming(P, M), Cost(M, V), V > 100.",
    },
    {
      id: "global-local-gate",
      policy: "Make a local delivery depend on global audit completion.",
      expected: false,
      source: "DenyReceive(P, M) :- Incoming(P, M), Finished(G).",
    },
    {
      id: "mint-capability",
      policy: "Let a model grant the permissions needed by its own action.",
      expected: false,
      source: "HasCap(P, C) :- Incoming(P, M), Requires(T, C).",
    },
  ];
  const compiled = probes.map(({ source, ...probe }) => {
    let accepted = true;
    const witnesses: { labels: number; expectedDeny: boolean; observedDeny: boolean }[] = [];
    let reason =
      "Accepted by the current extension compiler; syntax acceptance alone does not prove semantic implementation.";
    try {
      const artifact = createPolicyArtifact(
        novaDocuments(),
        [
          { id: "P1", basis: "builtin", datalog: "", notes: "Existing foundation" },
          { id: "P2", basis: "builtin", datalog: "", notes: "Existing foundation" },
          {
            id: "P3",
            basis: "extension",
            datalog: source,
            notes: "Synthetic compiler boundary probe, not translation output",
          },
          { id: "P4", basis: "builtin", datalog: "", notes: "Existing gate" },
          {
            id: "P5",
            basis: "builtin",
            datalog: "",
            notes: "Coverage not evaluated by this compiler probe",
          },
        ],
        "synthetic expressiveness probe",
      );
      if (["two-part-limit", "four-part-limit"].includes(probe.id)) {
        const threshold = probe.id === "two-part-limit" ? 2 : 4;
        for (const count of [threshold - 1, threshold]) {
          const tags = Array.from({ length: count }, (_, i) => `part${i}`);
          const facts = runSouffle(
            [
              f("Incoming", "auditor_a", "candidate"),
              ...tags.map((tag) => f("TransportTag", "candidate", tag)),
              ...tags.map((tag) => f("TagGroup", tag, "synthetic")),
            ],
            localRules("auditor_a", { policy: artifact }),
          ).facts;
          witnesses.push({
            labels: count,
            expectedDeny: count >= threshold,
            observedDeny: facts.some((f) => f.predicate === "DenyReceive"),
          });
        }
      }
    } catch (error) {
      accepted = false;
      reason = error instanceof Error ? error.message : "Rejected";
    }
    return {
      ...probe,
      accepted,
      reason,
      witnesses,
      matchedExpectation:
        accepted === probe.expected && witnesses.every((w) => w.expectedDeny === w.observedDeny),
    };
  });
  return {
    scope:
      "Five checked-in Nova policies plus eight synthetic boundary probes; no estimate of the fraction of real-world policies supported",
    currentPolicies: [
      {
        id: "P1",
        implementation: "fixed rules plus trusted ingestion and send instrumentation",
        witness: "forwarding and denied-message lineage probes",
      },
      {
        id: "P2",
        implementation: "fixed capability rule plus authoritative configuration and receive gate",
        witness: "bounded decisions and revocation probe",
      },
      {
        id: "P3",
        implementation: "three application denial rules plus local successful-receipt history",
        witness: "bounded decisions and workflow permutations",
      },
      {
        id: "P4",
        implementation: "receive lifecycle, payload boundary and success-only observation",
        witness: "actual accessible payload, receipt and forwarding checks",
      },
      {
        id: "P5",
        implementation: "local coverage plus authorized global observer",
        witness: "independent completion monitor versus observer output",
      },
    ],
    boundaries: [
      {
        policy: "Guarantee eventual completion of every legal workflow",
        limitation:
          "A legal choice can lead to a dead end; a receive gate does not supply an agent strategy or liveness guarantee.",
      },
      {
        policy: "Recognize confidential meaning in arbitrary unobserved tool output",
        limitation:
          "Requires trusted source observations; labels do not discover semantic content.",
      },
      {
        policy: "Forget a payload or remove a label after semantic sanitization",
        limitation: "No trusted declassification or unlearning mechanism is implemented.",
      },
      {
        policy: "Enforce a quota across independently running workers",
        limitation:
          "Requires shared transactional state or a coordination protocol; session serialization is local.",
      },
    ],
    compiled,
    publicSample,
  };
}

import { readFileSync } from "node:fs";
