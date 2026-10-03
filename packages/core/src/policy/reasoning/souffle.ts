import { execFileSync } from "node:child_process";
import { mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { PolicyFact } from "@rakazo/contracts";
import type { Rule } from "../datalog.js";
import type { ProofNode } from "./analysis.js";

// Only serialize our parsed AST. Never execute user-supplied Soufflé directives or shell text.
const quote = (value: string) => JSON.stringify(value);
const term = (value: string) =>
  /^[A-Z]/.test(value)
    ? value.replace("Anon$", "_NovaAnon")
    : quote(value.startsWith("c:") ? value.slice(2) : value);
const atom = (fact: PolicyFact, ground = false) =>
  `${fact.predicate}(${fact.args.map(ground ? quote : term).join(", ")})`;
export function souffleProgram(input: PolicyFact[], rules: Rule[]) {
  const arities = new Map<string, number>();
  for (const f of [...input, ...rules.flatMap((r) => [r.head, ...r.body])]) {
    if (!/^[A-Za-z][A-Za-z0-9_]*$/.test(f.predicate)) throw new Error("Invalid predicate.");
    if (arities.has(f.predicate) && arities.get(f.predicate) !== f.args.length)
      throw new Error(`Inconsistent arity: ${f.predicate}`);
    arities.set(f.predicate, f.args.length);
  }
  const declarations = [...arities].map(
    ([name, arity]) =>
      `.decl ${name}(${Array.from({ length: arity }, (_, i) => `a${i}:symbol`).join(", ")})`,
  );
  const outputs = [...new Set(rules.map((r) => r.head.predicate))].map(
    (name) => `.output ${name}(IO=file, rfc4180=true)`,
  );
  return [
    ...declarations,
    ...outputs,
    ...input.map((f) => `${atom(f, true)}.`),
    ...rules.map(
      (r) =>
        `// ${r.id}\n${atom(r.head)} :- ${[
          ...r.body.map((b) => `${b.negative ? "!" : ""}${atom(b)}`),
          ...r.distinct.map(([a, b]) => `${term(a)} != ${term(b)}`),
        ].join(", ")}.`,
    ),
  ].join("\n");
}

function execute(program: string, commands?: string) {
  const directory = mkdtempSync(join(tmpdir(), "nova-souffle-"));
  try {
    const file = join(directory, "program.dl");
    writeFileSync(file, program);
    let stdout: string;
    try {
      stdout = execFileSync(
        "prlimit",
        [
          "--as=1073741824",
          "--cpu=5",
          "--fsize=8388608",
          "--",
          "souffle",
          "-j",
          "1",
          "-D",
          directory,
          ...(commands ? ["-t", "explain"] : []),
          file,
        ],
        {
          encoding: "utf8",
          input: commands,
          timeout: 7000,
          maxBuffer: 4 * 1024 * 1024,
          stdio: ["pipe", "pipe", "pipe"],
        },
      );
    } catch (error) {
      const failure = error as { stderr?: string; signal?: string; code?: string };
      const detail = String(failure.stderr ?? "")
        .replaceAll(directory, "<program>")
        .slice(0, 3000);
      throw new Error(
        `Soufflé evaluation failed${failure.signal || failure.code ? " (resource limit or process error)" : ""}: ${detail || "Check that Soufflé is installed; simplify the query if it exceeded the execution limit."}`,
      );
    }
    const facts = readdirSync(directory)
      .filter((name) => name.endsWith(".csv"))
      .flatMap((name) =>
        csv(readFileSync(join(directory, name), "utf8")).map((args) => ({
          predicate: name.slice(0, -4),
          args,
        })),
      );
    if (facts.length > 10_000) throw new Error("Soufflé result exceeds 10,000 tuples.");
    return { stdout, facts };
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}
// Soufflé 2.5 RFC4180 adds a backslash before each doubled quote
// (WriteStreamCSV::outputSymbol). Nullary true is written as ().
function csv(source: string): string[][] {
  if (source === "()\n") return [[]];
  const rows: string[][] = [];
  let row: string[] = [],
    value = "",
    quoted = false;
  for (let i = 0; i < source.length; i++) {
    const c = source[i];
    if (c === '"') {
      if (quoted && source[i + 1] === '"') {
        value = value.slice(0, -1) + '"';
        i++;
      } else quoted = !quoted;
    } else if (!quoted && (c === "," || c === "\n")) {
      row.push(value);
      value = "";
      if (c === "\n") {
        rows.push(row);
        row = [];
      }
    } else if (c !== "\r" || quoted) value += c;
  }
  return rows;
}
const cache = new Map<string, PolicyFact[]>();
export function runSouffle(input: PolicyFact[], rules: Rule[]) {
  const program = souffleProgram(input, rules);
  let derived = cache.get(program);
  if (!derived) {
    derived = execute(program).facts;
    if (cache.size >= 128) cache.delete(cache.keys().next().value!);
    cache.set(program, derived);
  }
  const unique = new Map([...input, ...derived].map((f) => [JSON.stringify(f), f]));
  return { facts: structuredClone([...unique.values()]) };
}
type NativeNode = {
  premises?: string;
  axiom?: string;
  "rule-number"?: string;
  children?: NativeNode[];
};
export function explainSouffle(input: PolicyFact[], rules: Rule[], target: PolicyFact): ProofNode {
  const result = execute(
    souffleProgram(input, rules),
    `format json\nsetdepth 1000\nexplain ${atom(target, true)}\nexit\n`,
  );
  const native = JSON.parse(result.stdout) as {
    proof: NativeNode;
    rules: { "rule-number": string; rule: string }[];
  };
  const walk = (node: NativeNode): ProofNode => {
    const fact = node.premises ?? node.axiom ?? "Soufflé subproof";
    const predicate = fact.split("(")[0];
    const rule = native.rules.find(
      (r) => r["rule-number"] === node["rule-number"] && r.rule.startsWith(`${predicate}(`),
    );
    return {
      fact,
      kind: node.premises
        ? "derived"
        : fact.startsWith("!")
          ? "absence"
          : /!=| = | < | > /.test(fact)
            ? "comparison"
            : "input",
      rule: rule ? `${node["rule-number"]} ${rule.rule}` : node["rule-number"],
      children: (node.children ?? []).map(walk),
    };
  };
  return walk(native.proof);
}
