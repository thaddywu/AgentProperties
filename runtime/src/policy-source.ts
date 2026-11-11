import type { RuntimeBinding } from "./binding.js";
import type { PolicyFact } from "./datalog.js";
import { parseGroundFacts } from "./query.js";

function policyLine(line: string) {
  const masked = line.replace(/"(?:\\.|[^"\\])*"/g, (value) => " ".repeat(value.length));
  const positions = [masked.indexOf("//"), masked.indexOf("%")].filter((index) => index >= 0);
  const end = positions.length ? Math.min(...positions) : line.length;
  const code = line.slice(0, end);
  return {
    code,
    comment: line.slice(end + (line.slice(end, end + 2) === "//" ? 2 : 1)),
    syntax: code.replace(/"(?:\\.|[^"\\])*"/g, '""'),
  };
}

/** Parse schema declarations as data; never forward native directives to Souffle. */
export function readPolicySource(source: string) {
  if (source.length > 64_000) throw new Error("Policy document exceeds 64,000 characters.");
  const predicates: RuntimeBinding["predicates"] = {};
  const inputs = new Set<string>();
  const keys = new Map<string, string[]>();
  const lines = source.split("\n").map((line) => {
    const parsed = policyLine(line);
    const code = parsed.code;
    const comment = parsed.comment.trim();
    if (!code.trimStart().startsWith(".")) return /^(?:\/\/|%)/.test(line.trimStart()) ? "" : line;
    const declaration = /^\s*\.decl\s+([A-Za-z][A-Za-z_0-9]*)\s*\(([^()]*)\)\s*$/.exec(code);
    const input = /^\s*\.input\s+([A-Za-z][A-Za-z_0-9]*)\s*$/.exec(code);
    const key = /^\s*\.key\s+([A-Za-z][A-Za-z_0-9]*)\s*\(([^()]*)\)\s*$/.exec(code);
    if (key) {
      if (keys.has(key[1]!)) throw new Error("Duplicate key declaration.");
      keys.set(key[1]!, key[2]!.trim() ? key[2]!.split(",").map((field) => field.trim()) : []);
    } else if (declaration) {
      const name = declaration[1]!;
      if (Object.hasOwn(predicates, name) || Object.keys(predicates).length >= 64)
        throw new Error("Duplicate or excessive predicate declarations.");
      const args: string[] = [];
      const types: ("symbol" | "number")[] = [];
      for (const field of declaration[2]!.trim() ? declaration[2]!.split(",") : []) {
        const match = /^\s*([A-Za-z][A-Za-z_0-9]*)\s*:\s*(symbol|number)\s*$/.exec(field);
        if (!match || args.includes(match[1]!) || args.length >= 8)
          throw new Error("Declare distinct symbol/number arguments (at most eight).");
        args.push(match[1]!);
        types.push(match[2] as "symbol" | "number");
      }
      predicates[name] = { kind: "derived", args, meaning: comment || name };
      if (types.includes("number")) predicates[name]!.types = types;
    } else if (input) {
      if (inputs.has(input[1]!)) throw new Error("Duplicate input declaration.");
      inputs.add(input[1]!);
    } else throw new Error("Only .decl, .input and .key declarations are admitted.");
    return "";
  });
  for (const name of inputs) {
    if (!Object.hasOwn(predicates, name))
      throw new Error("Every .input needs a .decl in the same policy file.");
    predicates[name]!.kind = "input";
  }
  for (const [name, key] of keys) {
    const schema = predicates[name];
    if (
      schema?.kind !== "input" ||
      new Set(key).size !== key.length ||
      key.some((field) => !schema.args.includes(field))
    )
      throw new Error("Keys must name distinct fields of a declared input relation.");
    schema.key = key;
  }
  return { predicates, rules: lines.join("\n") };
}

export function readPolicyDocument(source: string) {
  const parsed = readPolicySource(source);
  const configuration: PolicyFact[] = [];
  let inRule = false;
  const rules = parsed.rules
    .split("\n")
    .map((line) => {
      const parsed = policyLine(line);
      const code = parsed.code.trim();
      if (inRule || parsed.syntax.includes(":-")) {
        inRule = !code.endsWith(".");
        return line;
      }
      if (/^\s*[A-Za-z][A-Za-z_0-9]*\s*\(.*\)\s*\.\s*$/.test(code)) {
        configuration.push(...parseGroundFacts(code));
        return "";
      }
      return line;
    })
    .join("\n");
  return { ...parsed, rules, configuration };
}
