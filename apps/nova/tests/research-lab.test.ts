import { readFileSync } from "node:fs";
import { parsePolicyRules } from "@rakazo/policy-runtime/query";
import { describe, expect, it } from "vitest";
import { recursiveComparison } from "../src/evaluation/recursive.js";
import {
  createRoutingEpisode,
  InvalidRouteError,
  parseRoutes,
} from "../src/evaluation/routing-agent.js";
import { compareUcq } from "../src/evaluation/ucq.js";
import { readPolicyArtifact } from "../src/translated-policy.js";

describe("observable translation and execution lab", () => {
  it("proves positive UCQ equivalence despite variable names and duplicate body atoms", () => {
    const a = parsePolicyRules("Out(X) :- Edge(X,Y). Out(X) :- Seed(X).");
    const b = parsePolicyRules("Out(A) :- Seed(A). Out(A) :- Edge(A,B), Edge(A,B).");
    expect(compareUcq(a, b, "Out").status).toBe("equivalent");
    const difference = compareUcq(a, b.slice(1), "Out");
    expect(difference.status).toBe("different");
    expect(difference.referenceContainedInTranslated?.counterexample?.inputs).toHaveLength(1);
    expect(
      compareUcq(
        parsePolicyRules('Out(X) :- Edge(X,"cq_fresh_0").'),
        parsePolicyRules("Out(X) :- Edge(X,X)."),
        "Out",
      ).status,
    ).toBe("different");
  });
  it("does not claim a UCQ proof for negation, comparisons or recursive output", () => {
    for (const source of [
      "Out(X) :- Seed(X), not Blocked(X).",
      "Out(X) :- Edge(X,Y), X != Y.",
      "Out(X) :- Out(Y), Edge(Y,X).",
    ])
      expect(compareUcq(parsePolicyRules(source), parsePolicyRules(source), "Out").status).toBe(
        "unsupported",
      );
  });
  it("tests recursive propagation independently and finds the missing-rule control", () => {
    const artifact = readPolicyArtifact(
      JSON.parse(
        readFileSync(new URL("../evaluation/model-trials/trial-1.json", import.meta.url), "utf8"),
      ),
    );
    const trial = recursiveComparison(artifact);
    expect(trial.snapshots).toBe(2048);
    expect(trial.oracleMismatches).toBe(0);
    expect(trial.mismatches.DenyReceive).toBeGreaterThan(0);
    expect(trial.byPriorState.no_prior_exposure!.mismatches.DenyReceive).toBe(0);
    expect(trial.byPriorState.already_exposed!.mismatches.DenyReceive).toBeGreaterThan(0);
    expect(trial.mismatches.Covered).toBeGreaterThan(0);
    const control = recursiveComparison(artifact, true);
    expect(control.mismatches.DenyReceive).toBeGreaterThan(0);
  });
  it("counts actual forbidden deliveries separately from incomplete protected workflows", async () => {
    for (const mode of ["disabled", "reference"] as const) {
      const episode = await createRoutingEpisode(mode);
      for (const sender of ["procurement", "facility", "hr"])
        await episode.attempt({ sender, recipient: "auditor_a" });
      const result = episode.result();
      expect(result.completed).toBe(mode === "disabled");
      expect(result.violations).toBe(mode === "disabled" ? 1 : 0);
      expect(result.falseDenials).toBe(0);
      expect(result.deniedPayloadLeaks).toBe(0);
    }
    const safe = await createRoutingEpisode("reference");
    for (const [sender, recipient] of [
      ["procurement", "auditor_a"],
      ["facility", "auditor_b"],
      ["hr", "auditor_a"],
    ])
      await safe.attempt({ sender: sender!, recipient: recipient! });
    expect(safe.result().safelyCompleted).toBe(true);
    await expect(safe.attempt({ sender: "hr", recipient: "auditor_b" })).rejects.toBeInstanceOf(
      InvalidRouteError,
    );
    expect(() => parseRoutes('{"routes":[{"sender":1}]}')).toThrow();
  });
});
