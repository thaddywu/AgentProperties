import { describe, expect, it } from "vitest";
import { emptyPolicyState } from "./protocol.js";
import { queryPolicyStores } from "./query.js";

const fixture = () => {
  const stores = emptyPolicyState().local;
  stores.board.facts = [
    { predicate: "Edge", args: ["A", "B"] },
    { predicate: "Edge", args: ["B", "C"] },
  ];
  stores.procurement.facts = [{ predicate: "Received", args: ["procurement", "m"] }];
  stores.hiring.facts = [{ predicate: "Carries", args: ["m", "nova", "hiring"] }];
  return stores;
};
describe("read-only Datalog programs", () => {
  it("supports new predicates, recursive rules, quoted constants and joins", () => {
    const stores = fixture(),
      before = JSON.stringify(stores);
    const result = queryPolicyStores(
      stores,
      "board",
      `
      Path(X, Y) :- Edge(X, Y).
      Path(X, Z) :- Path(X, Y), Edge(Y, Z).
      ?- Path("A", Y).
    `,
    );
    expect(result).toEqual({ columns: ["Y"], rows: [["B"], ["C"]] });
    expect(JSON.stringify(stores)).toBe(before);
  });
  it("supports temporary facts, safe negation, inequality and anonymous terms", () => {
    expect(
      queryPolicyStores(
        fixture(),
        "board",
        `
      Blocked("B").
      Reach(X) :- Edge(_, X), not Blocked(X), X != "A".
      ?- Reach(X).
    `,
      ).rows,
    ).toEqual([["C"]]);
  });
  it("evaluates real policy with temporary local inputs", () => {
    expect(
      queryPolicyStores(fixture(), "procurement", `Carries(m, nova, hiring). ?- Knows(A, P, C).`)
        .rows,
    ).toEqual([["procurement", "nova", "hiring"]]);
  });
  it("does not derive policy knowledge across global stores, but permits explicit analysis joins", () => {
    expect(queryPolicyStores(fixture(), "global", `?- Knows(A, P, C).`).rows).toEqual([]);
    expect(
      queryPolicyStores(
        fixture(),
        "global",
        `
      Combined(A, P, C) :- Store_Received(O, A, M), Store_Carries(S, M, P, C).
      ?- Combined(A, P, C).
    `,
      ).rows,
    ).toEqual([["procurement", "nova", "hiring"]]);
  });
  it("supports ground true/false and empty stores", () => {
    expect(queryPolicyStores(fixture(), "board", `?- Edge("A", "B").`).rows).toEqual([[]]);
    expect(queryPolicyStores(fixture(), "facility", `?- Knows(A, P, C).`).rows).toEqual([]);
  });
  it.each([
    ["P(X) :- not Q(X). ?- P(X).", /Unsafe/],
    ["P(X) :- Edge(X, Y), not Q(X). Q(X) :- Edge(X, Y), not P(X). ?- P(X).", /Unstratified/],
    ["?- Edge(X).", /arity/],
    ["Bad(X). ?- Bad(X).", /constants/],
    ["?- Edge(f(X), Y).", /Expected/],
    ["?- Edge(X, Y). process.exit()", /Expected/],
  ])("rejects invalid programs: %s", (program, error) => {
    expect(() => queryPolicyStores(fixture(), "board", program)).toThrow(error);
  });
  it("bounds combinatorial queries", () => {
    const facts = Array.from({ length: 45 }, (_, i) => `N(n${i}).`).join("\n");
    expect(() =>
      queryPolicyStores(
        fixture(),
        "board",
        `${facts} Huge(A, B, C, D) :- N(A), N(B), N(C), N(D). ?- Huge(A, B, C, D).`,
      ),
    ).toThrow(/limit/);
  });
});
