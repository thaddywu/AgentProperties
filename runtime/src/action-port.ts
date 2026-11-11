import type {
  ActionContext,
  ActionTransaction,
  EffectOutcome,
  PolicyBundle,
} from "./application.js";
import { createPolicySession, EffectNotAppliedError, EffectUncertainError } from "./application.js";
import type { ActionIntent } from "./binding.js";
import { readRuntimeBinding } from "./binding.js";
import type { PolicyFact } from "./datalog.js";
import { LIFECYCLE_INPUT_ARITIES } from "./lifecycle.js";
import type { ObservationSnapshot } from "./observations.js";

export type ActionObservation = {
  id: string;
  predicates: readonly string[];
  read: (context: ActionContext) => Promise<ObservationSnapshot>;
};
export type RegisteredOperation = {
  action: string;
  /** Successful events this operation may produce; source/configuration inputs are separate. */
  observations?: readonly string[];
  execute: (context: ActionContext) => Promise<EffectOutcome<unknown>>;
};
export type BoundActionResult =
  | { allowed: false; attemptId: string }
  | { allowed: true; attemptId: string; value: unknown };

/** Trusted application integration. Only bind(...).execute is handed to an agent. */
export function createActionPort(options: {
  binding: unknown;
  bundle: PolicyBundle;
  inputs?: PolicyFact[];
  observations?: readonly ActionObservation[];
  operations: readonly RegisteredOperation[];
  transaction?: ActionTransaction;
}) {
  const binding = readRuntimeBinding(options.binding);
  const session = createPolicySession(binding, options.bundle, options.inputs);
  const transaction = options.transaction;
  const admitted = (predicate: string) =>
    Object.hasOwn(binding.predicates, predicate) &&
    binding.predicates[predicate]!.kind === "input" &&
    ![binding.decision.request, binding.decision.parameters].includes(predicate) &&
    !(binding.mechanisms?.includes("fsm") && Object.hasOwn(LIFECYCLE_INPUT_ARITIES, predicate));
  const sourceInputs = new Set<string>();
  const sourceIds = new Set<string>();
  const sources = (options.observations ?? []).map((source) => {
    if (
      typeof source.id !== "string" ||
      !source.id ||
      source.id.length > 1024 ||
      sourceIds.has(source.id) ||
      !Array.isArray(source.predicates) ||
      !source.predicates.length
    )
      throw new Error("Observation sources need distinct identities and input declarations.");
    sourceIds.add(source.id);
    for (const predicate of source.predicates) {
      if (!admitted(predicate) || sourceInputs.has(predicate))
        throw new Error("Sources must own distinct, admitted input relations.");
      sourceInputs.add(predicate);
    }
    return { id: source.id, predicates: [...source.predicates], read: source.read };
  });
  const operations = new Map<string, RegisteredOperation>();
  for (const operation of options.operations) {
    if (
      typeof operation.action !== "string" ||
      !operation.action ||
      operation.action.length > 1024 ||
      operations.has(operation.action)
    )
      throw new Error("Operations need distinct, bounded action names.");
    if (operation.observations !== undefined && !Array.isArray(operation.observations))
      throw new Error("Operation events must be declared as an array.");
    const outputs = [...(operation.observations ?? [])];
    if (
      new Set(outputs).size !== outputs.length ||
      outputs.some((predicate) => !admitted(predicate) || sourceInputs.has(predicate))
    )
      throw new Error("Operation events cannot overwrite authoritative sources or runtime inputs.");
    operations.set(operation.action, { ...operation, observations: outputs });
  }
  if (!operations.size) throw new Error("Register at least one protected operation.");
  const execute = (intent: ActionIntent) => {
    const operation = operations.get(intent.action);
    if (!operation) throw new Error("Unknown protected operation.");
    return session.executeObserved(intent, {
      transaction,
      observe: async (context) => {
        const snapshots = [];
        for (const source of sources) {
          const snapshot = await source.read(context);
          snapshots.push({
            ...snapshot,
            facts: structuredClone(snapshot.facts),
            id: source.id,
            predicates: source.predicates,
          });
        }
        return snapshots;
      },
      effect: async (context) => {
        const outcome = await operation.execute(context);
        if (outcome?.status === "applied") {
          const observations = structuredClone(outcome.observations ?? []);
          if (observations.some((fact) => !operation.observations!.includes(fact.predicate)))
            throw new Error("An operation produced an undeclared successful event.");
          return { status: "applied", value: outcome.value, observations };
        }
        return outcome;
      },
    });
  };
  return {
    policyHash: session.policyHash,
    /** The backend resolves this identity from its authenticated execution context. */
    bind(principal: string) {
      if (typeof principal !== "string" || !principal.length || principal.length > 1024)
        throw new Error("An authenticated principal is required.");
      return {
        execute(
          action: string,
          resource?: string,
          parameters?: Record<string, string>,
        ): Promise<BoundActionResult> {
          // Capture/validate synchronously before queueing; redact backend evidence on completion.
          return execute({ actor: principal, action, resource, parameters })
            .then(
              (result): BoundActionResult =>
                result.allowed
                  ? { allowed: true, attemptId: result.decision.request.id, value: result.value }
                  : { allowed: false, attemptId: result.decision.request.id },
            )
            .catch((error: unknown) => {
              if (error instanceof EffectUncertainError)
                throw new EffectUncertainError(error.attemptId);
              if (error instanceof EffectNotAppliedError)
                throw new EffectNotAppliedError("Protected operation was not applied.");
              throw new Error("Protected operation failed before a result was confirmed.");
            });
        },
      };
    },
    // Administrator surface, never exposed as agent tools.
    execute,
    query: session.query,
    why: session.why,
    check: session.check,
    whatIf: session.whatIf,
    snapshot: session.snapshot,
  };
}
