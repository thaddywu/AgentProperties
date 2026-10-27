import { describe, expect, it } from "vitest";
import { queryDatalog } from "../src/query.js";

describe("application-independent policy queries", () => {
  it("runs recursive queries with uppercase symbols without an application or host", () => {
    const input = [
      { predicate: "Edge", args: ["A", "B"] },
      { predicate: "Edge", args: ["B", "C"] },
    ];
    expect(
      queryDatalog(
        input,
        [],
        'Path(X,Y) :- Edge(X,Y). Path(X,Z) :- Path(X,Y), Edge(Y,Z). ?- Path("A", Y).',
      ).rows,
    ).toEqual([["B"], ["C"]]);
  });
  it("retains safe variable and stratification checks after extraction", () => {
    expect(() => queryDatalog([], [], "P(X) :- not Q(X). ?- P(X).")).toThrow(/Unsafe/);
    expect(() =>
      queryDatalog([], [], "P(X) :- Seed(X), not Q(X). Q(X) :- Seed(X), not P(X). ?- P(X)."),
    ).toThrow(/Unstratified/);
  });
});
