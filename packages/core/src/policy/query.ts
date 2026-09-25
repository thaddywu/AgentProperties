import type { PolicyFact, PolicyStores } from "@rakazo/contracts";
import type { Atom, Rule } from "./datalog.js";
import { APP2_RULES, evaluateDatalog, factKey } from "./datalog.js";

const isVariable = (s: string) => /^[A-Z]/.test(s);
const constant = (s: string) => `c:${s}`;
const decode = (s: string) => (s.startsWith("c:") ? s.slice(2) : s);
const limits = { operations: 500_000, facts: 10_000 };
const encodeFact = (f: PolicyFact): PolicyFact => ({ ...f, args: f.args.map(constant) });
const encodeRule = (r: Rule): Rule => {
  const term = (s: string) => (isVariable(s) ? s : constant(s));
  return {
    ...r,
    head: { ...r.head, args: r.head.args.map(term) },
    body: r.body.map((a) => ({ ...a, args: a.args.map(term) })),
    distinct: r.distinct.map(([a, b]) => [term(a), term(b)]),
  };
};

/** Text is parsed as data. No JavaScript, function terms or mutations are accepted. */
function parseProgram(source: string) {
  if (source.length > 20_000) throw new Error("Program is too long (20,000 characters maximum).");
  const tokens: string[] = [];
  const scanner =
    /\s+|\/\/[^\n]*|%[^\n]*|"(?:\\.|[^"\\])*"|:-|\?-|!=|[A-Za-z_][A-Za-z_0-9]*|-?\d+(?:\.\d+)?|[(),.]/gy;
  let offset = 0;
  while (offset < source.length) {
    scanner.lastIndex = offset;
    const match = scanner.exec(source);
    if (!match) throw new Error(`Unexpected character at position ${offset + 1}.`);
    offset = scanner.lastIndex;
    if (!/^\s|^\/\/|^%/.test(match[0])) tokens.push(match[0]);
  }
  let pos = 0,
    anonymous = 0;
  const peek = () => tokens[pos];
  const take = (expected?: string): string => {
    const value = tokens[pos++];
    if (!value || (expected && value !== expected))
      throw new Error(`Expected ${expected ?? "token"}, got ${value ?? "end of program"}.`);
    return value;
  };
  const term = () => {
    const value = take();
    if (value === "_") return `Anon$${anonymous++}`;
    if (value.startsWith('"')) return constant(JSON.parse(value));
    if (!/^(?:[A-Za-z_][A-Za-z_0-9]*|-?\d+(?:\.\d+)?)$/.test(value))
      throw new Error("Expected a variable or constant.");
    return isVariable(value) ? value : constant(value);
  };
  const atom = (): Atom => {
    const predicate = take();
    if (!/^[A-Za-z][A-Za-z_0-9]*$/.test(predicate) || predicate === "QueryResult")
      throw new Error("Invalid or reserved predicate name.");
    take("(");
    const args: string[] = [];
    if (peek() !== ")") {
      args.push(term());
      while (peek() === ",") {
        take();
        args.push(term());
      }
    }
    take(")");
    return { predicate, args };
  };
  const body = () => {
    const atoms: Atom[] = [],
      distinct: [string, string][] = [];
    do {
      if (peek() === ",") take();
      if (peek() === "not") {
        take();
        atoms.push({ ...atom(), negative: true });
      } else if (tokens[pos + 1] === "!=") {
        const a = term();
        take("!=");
        distinct.push([a, term()]);
      } else atoms.push(atom());
    } while (peek() === ",");
    return {
      body: [...atoms.filter((a) => !a.negative), ...atoms.filter((a) => a.negative)],
      distinct,
    };
  };
  const facts: PolicyFact[] = [],
    rules: Rule[] = [];
  let columns: string[] | undefined;
  while (peek()) {
    if (peek() === "?-") {
      if (columns) throw new Error("Use one query per execution.");
      take();
      const parts = body();
      columns = [
        ...new Set([...parts.body.flatMap((a) => a.args), ...parts.distinct.flat()]),
      ].filter((v) => isVariable(v) && !v.startsWith("Anon$"));
      rules.push({
        id: "query",
        head: { predicate: "QueryResult", args: columns },
        ...parts,
        stratum: 0,
      });
      take(".");
    } else {
      const head = atom();
      if (peek() === ":-") {
        take();
        rules.push({ id: `user_${rules.length}`, head, ...body(), stratum: 0 });
      } else {
        if (head.args.some(isVariable))
          throw new Error("Facts must contain constants; quote uppercase constants.");
        facts.push(head);
      }
      take(".");
    }
  }
  if (!columns) throw new Error("End with a query, for example: ?- Knows(A, P, C).");
  if (rules.length > 100) throw new Error("At most 100 rules are supported per execution.");
  return { facts, rules, columns };
}

function validateAndStratify(facts: PolicyFact[], rules: Rule[]) {
  const arities = new Map<string, number>();
  for (const atom of [...facts, ...rules.flatMap((r) => [r.head, ...r.body])]) {
    const arity = arities.get(atom.predicate);
    if (arity !== undefined && arity !== atom.args.length)
      throw new Error(`Inconsistent arity for ${atom.predicate}.`);
    arities.set(atom.predicate, atom.args.length);
  }
  for (const rule of rules) {
    const bound = new Set(
      rule.body
        .filter((a) => !a.negative)
        .flatMap((a) => a.args)
        .filter(isVariable),
    );
    for (const value of [
      ...rule.head.args,
      ...rule.body.filter((a) => a.negative).flatMap((a) => a.args),
      ...rule.distinct.flat(),
    ])
      if (isVariable(value) && !bound.has(value))
        throw new Error(`Unsafe variable ${value}: bind it in a positive atom.`);
  }
  const strata = new Map([...arities.keys()].map((p) => [p, 0]));
  for (let i = 0; i <= strata.size; i++) {
    let changed = false;
    for (const r of rules)
      for (const a of r.body) {
        const required = strata.get(a.predicate)! + (a.negative ? 1 : 0);
        if (required > strata.get(r.head.predicate)!) {
          strata.set(r.head.predicate, required);
          changed = true;
        }
      }
    if (!changed) {
      for (const r of rules) r.stratum = strata.get(r.head.predicate)!;
      return;
    }
  }
  throw new Error("Unstratified negation: a negative dependency is recursive.");
}

export function queryPolicyStores(stores: PolicyStores, scope: string, source: string) {
  const parsed = parseProgram(source);
  const global = scope === "global";
  if (!global && !Object.hasOwn(stores, scope)) throw new Error("Unknown principal.");
  const selected = global
    ? Object.entries(stores)
    : Object.entries(stores).filter(([id]) => id === scope);
  const facts = new Map<string, PolicyFact>();
  for (const [owner, store] of selected) {
    // Policy closure is computed locally, never by combining principals' knowledge.
    const closed = evaluateDatalog(
      store.facts.map(encodeFact),
      APP2_RULES.map(encodeRule),
      limits,
    ).facts;
    for (const f of closed) {
      facts.set(factKey(f), f);
      const owned = { predicate: `Store_${f.predicate}`, args: [constant(owner), ...f.args] };
      facts.set(factKey(owned), owned);
    }
  }
  const input = [...facts.values(), ...parsed.facts];
  const rules = [...APP2_RULES.map(encodeRule), ...parsed.rules];
  // Global includes local policy results; only explicit user rules combine stores.
  const active = global ? parsed.rules : rules;
  validateAndStratify(input, active);
  const result = evaluateDatalog(input, active, limits);
  return {
    columns: parsed.columns,
    rows: result.facts.filter((f) => f.predicate === "QueryResult").map((f) => f.args.map(decode)),
  };
}
