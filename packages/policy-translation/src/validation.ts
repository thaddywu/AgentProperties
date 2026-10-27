import { spawnSync } from "node:child_process";
import type { Rule } from "@rakazo/core";
import { parseProgram, queryDatalog } from "@rakazo/core/policy/query";
import { runSouffle } from "@rakazo/core/policy/reasoning/souffle";
import { NOVA_PREDICATES } from "./prompt.js";

export type Validation = {
  status:
    | "valid_translation_output"
    | "syntax_or_compilation_failure"
    | "unsupported_schema"
    | "validation_blocked";
  message: string;
  typescript: "passed" | "not_run";
  souffle: "passed" | "failed" | "not_run";
};

export function parseDatalog(source: string): {
  rules: Rule[];
  facts: ReturnType<typeof parseProgram>["facts"];
} {
  const parsed = parseProgram(`${source}\n?- TranslationSentinel().`);
  // The appended query is only for the existing parser; it is never part of model output.
  return { facts: parsed.facts, rules: parsed.rules.filter((rule) => rule.id !== "query") };
}

export function validateDatalog(source: string): Validation {
  let parsed: ReturnType<typeof parseDatalog>;
  try {
    parsed = parseDatalog(source);
  } catch (error) {
    return {
      status: "syntax_or_compilation_failure",
      message: String(error),
      typescript: "not_run",
      souffle: "not_run",
    };
  }
  for (const atom of [
    ...parsed.facts,
    ...parsed.rules.flatMap((rule) => [rule.head, ...rule.body]),
  ]) {
    const schema = Object.hasOwn(NOVA_PREDICATES, atom.predicate)
      ? NOVA_PREDICATES[atom.predicate as keyof typeof NOVA_PREDICATES]
      : undefined;
    if (!schema || schema.args.length !== atom.args.length)
      return {
        status: "unsupported_schema",
        message: `Unknown predicate or wrong arity: ${atom.predicate}/${atom.args.length}`,
        typescript: "not_run",
        souffle: "not_run",
      };
  }
  for (const head of [...parsed.facts, ...parsed.rules.map((rule) => rule.head)]) {
    if (NOVA_PREDICATES[head.predicate as keyof typeof NOVA_PREDICATES].kind === "input")
      return {
        status: "unsupported_schema",
        message: `Runtime input cannot be written by policy: ${head.predicate}`,
        typescript: "not_run",
        souffle: "not_run",
      };
  }
  try {
    // Reuse existing safety, stratification and bounded evaluation. No reference rules are supplied.
    queryDatalog([], [], `${source}\n?- TranslationSentinel().`);
  } catch (error) {
    return {
      status: "syntax_or_compilation_failure",
      message: String(error),
      typescript: "not_run",
      souffle: "not_run",
    };
  }
  if (
    ["souffle", "prlimit"].some(
      (command) => spawnSync(command, ["--version"], { timeout: 3000 }).status !== 0,
    )
  )
    return {
      status: "validation_blocked",
      message:
        "TypeScript checks passed; native Nova validation requires souffle and Linux prlimit on PATH.",
      typescript: "passed",
      souffle: "not_run",
    };
  try {
    runSouffle(
      parsed.facts.map((fact) => ({ ...fact, args: fact.args.map((arg) => arg.slice(2)) })),
      parsed.rules,
    );
    return {
      status: "valid_translation_output",
      message:
        "Syntax/schema and empty-input engine checks passed; semantic correctness is unproven.",
      typescript: "passed",
      souffle: "passed",
    };
  } catch (error) {
    return {
      status: "syntax_or_compilation_failure",
      message: String(error),
      typescript: "passed",
      souffle: "failed",
    };
  }
}
