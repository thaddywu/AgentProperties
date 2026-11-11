import { expect, it } from "vitest";
import { parsePolicyRules, queryDatalog } from "../src/query.js";
import { runSouffle } from "../src/souffle.js";

it("compares canonical integers exactly beyond floating-point precision", () => {
  const input = ["9007199254740993", "9007199254740992", "-1", "10", "01"].map((value) => ({
    predicate: "Value",
    args: [value],
  }));
  expect(queryDatalog(input, [], "?- Value(N), N > 9007199254740992.").rows).toEqual([
    ["9007199254740993"],
  ]);
  expect(queryDatalog(input, [], "?- Value(N), N >= 0, N <= 10.").rows).toEqual([["10"]]);
});
it("rejects comparisons with unbound variables", () => {
  expect(() => queryDatalog([], [], "?- Value(N), N < Unknown.")).toThrow("Unsafe");
});

it("uses the same exact integer comparison in native Souffle without exposing comparison facts", () => {
  const input = ["9007199254740993", "9007199254740992", "9223372036854775808", "01"].map(
    (value) => ({ predicate: "Value", args: [value] }),
  );
  const rules = parsePolicyRules("Large(N) :- Value(N), N > 9007199254740992.");
  expect(runSouffle(input, rules).facts.filter((fact) => fact.predicate === "Large")).toEqual([
    { predicate: "Large", args: ["9007199254740993"] },
  ]);
});
