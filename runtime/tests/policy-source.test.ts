import { expect, it } from "vitest";
import { compileApplicationPolicy } from "../src/application.js";
import { readRuntimeBinding, validateInputs } from "../src/binding.js";
import { readPolicyDocument, readPolicySource } from "../src/policy-source.js";
import { binding, policy } from "./fixtures/action-contract.js";

it("keeps the last atom of a multiline rule out of static configuration", () => {
  expect(
    readPolicyDocument(
      '.decl Text(Value:symbol)\n.input Text\nText("https://example.invalid/a:-b"). // comment',
    ).configuration,
  ).toEqual([{ predicate: "Text", args: ["https://example.invalid/a:-b"] }]);
  const source = `// A comment containing :- is not a clause.
.decl Grant(Actor:symbol, Resource:symbol)
.input Grant
Grant("reader", "item").
Allow(Q) :-
    Request(Q, P, "read"),
    Parameter(Q, "resource", R),
    Grant(P, R).`;
  expect(readPolicyDocument(source).configuration).toEqual([
    { predicate: "Grant", args: ["reader", "item"] },
  ]);
  expect(
    compileApplicationPolicy(
      { ...binding, tests: [], configuration: readPolicyDocument(source).configuration },
      source,
    ).source,
  ).toBe(source);
});

it("keeps application vocabulary beside rules and validates it against the trusted binding", () => {
  const source = `.decl Grant(Actor:symbol, Resource:symbol) // Backend grants.
.input Grant
.decl Version(Resource:symbol, Version:symbol)
.input Version
${policy}`;
  expect(readPolicySource(source).predicates.Grant).toEqual({
    kind: "input",
    args: ["Actor", "Resource"],
    meaning: "Backend grants.",
  });
  expect(compileApplicationPolicy(binding, source).source).toBe(source);
  expect(() => compileApplicationPolicy(binding, source.replace(".input Grant", ""))).toThrow(
    "declarations do not match",
  );
  expect(() =>
    compileApplicationPolicy(binding, source.replace("Actor:symbol", "Impostor:symbol")),
  ).toThrow("declarations do not match");
});

it("keeps number field declarations and rejects malformed numeric input facts", () => {
  expect(
    readPolicySource(".decl Quantity(Value:number)\n.input Quantity").predicates.Quantity?.types,
  ).toEqual(["number"]);
  const typed = readRuntimeBinding(binding);
  typed.predicates.Quantity = {
    kind: "input",
    args: ["Value"],
    types: ["number"],
    meaning: "Canonical quantity.",
  };
  for (const value of ["01", "not-a-number", "9223372036854775808"])
    expect(() => validateInputs(typed, [{ predicate: "Quantity", args: [value] }])).toThrow(
      "Numeric",
    );
});

it.each([
  '.include "private"',
  '.input Grant(IO=file, filename="private")',
  ".decl Grant(A:float)",
  ".decl Grant(A:symbol, A:symbol)",
  ".decl Grant(A:symbol)\n.decl Grant(B:symbol)",
  ".input Grant",
  ".decl Grant(A:symbol)\n.input Grant\n.input Grant",
  ".output Grant",
])("rejects undeclared inputs, duplicate schemas and native directives: %s", (source) => {
  expect(() => readPolicySource(source)).toThrow();
});

it("declares mutable relation keys including a singleton and checks uniqueness", () => {
  const source = `.decl Account(Id:symbol, Balance:number)
.input Account
.key Account(Id)
.decl Clock(Now:number)
.input Clock
.key Clock()`;
  const parsed = readPolicySource(source).predicates;
  expect(parsed.Account?.key).toEqual(["Id"]);
  expect(parsed.Clock?.key).toEqual([]);
  const typed = readRuntimeBinding(binding);
  Object.assign(typed.predicates, parsed);
  expect(() =>
    validateInputs(typed, [
      { predicate: "Clock", args: ["1"] },
      { predicate: "Clock", args: ["2"] },
    ]),
  ).toThrow("Conflicting keyed");
  expect(() => readPolicySource(source.replace("Account(Id)", "Account(Missing)"))).toThrow("Keys");
});
