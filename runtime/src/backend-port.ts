import { EffectNotAppliedError } from "./application.js";
import type { PolicyFact } from "./datalog.js";
import type { MessagingProfile, PolicyMessage } from "./messaging.js";
import { createMessagingRuntime, MessagingRuntime } from "./messaging.js";

export type ObservationBinding = {
  id: string;
  predicates: string[];
  scope: string;
  read: () => Promise<{ version: string; complete: boolean; facts: PolicyFact[] }>;
};
export class DeliveryRecoveryRequiredError extends Error {
  constructor(public readonly messageId: string) {
    super("Delivery outcome requires reconciliation.");
  }
}

/** The backend calls this trusted surface; agents receive only a principal-bound intent port. */
export function createBackendPort(options: {
  profile: MessagingProfile;
  observations?: ObservationBinding[];
  deliver: (message: Readonly<PolicyMessage>) => Promise<void>;
}) {
  const runtime = createMessagingRuntime(options.profile);
  let queue: Promise<unknown> = Promise.resolve();
  let pending = 0;
  let recovery: { id: string; confirmed: typeof runtime } | undefined;
  const observedPredicates = new Set<string>();
  const runtimeInputs = new Set([
    runtime.profile.roles.sender,
    runtime.profile.roles.received,
    runtime.profile.roles.incoming,
    runtime.profile.roles.order,
    runtime.profile.roles.source,
    runtime.profile.roles.imported,
  ]);
  for (const binding of options.observations ?? []) {
    if (!binding.id || !binding.scope || !binding.predicates.length)
      throw new Error("An observation source needs identity, scope and predicates.");
    for (const predicate of binding.predicates) {
      if (
        runtimeInputs.has(predicate) ||
        runtime.profile.predicates[predicate]?.kind !== "input" ||
        observedPredicates.has(predicate)
      )
        throw new Error(
          "Observation producers must have distinct admitted input relations and cannot forge runtime events.",
        );
      observedPredicates.add(predicate);
    }
  }
  const exclusive = <T>(operation: () => Promise<T>) => {
    pending++;
    const run = queue.then(async () => {
      try {
        return await operation();
      } finally {
        pending--;
      }
    });
    queue = run.catch(() => {});
    return run;
  };
  const available = () => {
    if (recovery) throw new DeliveryRecoveryRequiredError(recovery.id);
  };
  const refresh = async () => {
    const observations: PolicyFact[] = [];
    const versions: Record<string, string> = {};
    for (const binding of options.observations ?? []) {
      const snapshot = await binding.read();
      if (!snapshot.complete || !snapshot.version?.trim())
        throw new Error(`Incomplete or unversioned observation: ${binding.id}`);
      if (snapshot.facts.some((fact) => !binding.predicates.includes(fact.predicate)))
        throw new Error("Observation producer wrote an undeclared relation.");
      observations.push(...snapshot.facts);
      versions[binding.id] = snapshot.version;
    }
    if (observedPredicates.size)
      runtime.configure([
        ...Object.values(runtime.state.stores)
          .flat()
          .filter((row) => row.source === "config" && !observedPredicates.has(row.fact.predicate))
          .map((row) => row.fact),
        ...observations,
      ]);
    return versions;
  };
  const dispatch = (
    from: string,
    to: string,
    id: string,
    body: string,
    trusted?: { tag: string },
  ) =>
    exclusive(async () => {
      available();
      const versions = await refresh();
      const existing = runtime.state.messages.find((message) => message.id === id);
      if (existing) {
        if (
          existing.from !== from ||
          existing.to !== to ||
          existing.body !== body ||
          (trusted && !existing.labels.some((label) => label.args[1] === trusted.tag))
        )
          throw new Error(
            "Message identity cannot be reused for different contents or source labels.",
          );
        if (existing.status !== "pending")
          return {
            allowed: existing.status === "delivered",
            replayed: true,
            message: structuredClone(existing),
            versions,
          };
      } else runtime.send(from, to, id, body, trusted);
      const trial = new MessagingRuntime(runtime.profile, runtime.snapshot());
      const decision = trial.settle(id);
      if (!decision.allowed) {
        runtime.state = trial.state;
        return { ...decision, versions, replayed: false };
      }
      try {
        await options.deliver(structuredClone(decision.message));
      } catch (error) {
        if (error instanceof EffectNotAppliedError) throw error;
        recovery = { id, confirmed: trial };
        throw new DeliveryRecoveryRequiredError(id);
      }
      runtime.state = trial.state;
      return { ...decision, versions, replayed: false };
    });
  return {
    /** Identity must come from authentication/run context, not from model arguments. */
    bind(principal: string) {
      if (!runtime.profile.principals.includes(principal))
        throw new Error("Unknown authenticated principal.");
      return {
        send: (to: string, id: string, body: string) => dispatch(principal, to, id, body),
        accessible: () => runtime.accessible(principal),
        query(source: string) {
          if (pending)
            throw new Error("Await the current operation before inspecting committed facts.");
          const state = runtime.snapshot();
          state.stores[principal] = state.stores[principal]!.filter(
            (row) => row.lifetime !== "temporary",
          );
          return new MessagingRuntime(runtime.profile, state).query(principal, source);
        },
      };
    },
    ingest(source: {
      authority: string;
      recipient: string;
      id: string;
      body: string;
      tag: string;
    }) {
      return dispatch(source.authority, source.recipient, source.id, source.body, {
        tag: source.tag,
      });
    },
    snapshot: () => runtime.snapshot(),
    inspect: () => runtime.inspect(),
    async reconcile(messageId: string, outcome: "delivered" | "not_delivered") {
      if (!["delivered", "not_delivered"].includes(outcome))
        throw new Error("Reconciliation requires a confirmed delivery outcome.");
      return exclusive(async () => {
        if (recovery?.id !== messageId) throw new Error("Unknown delivery recovery attempt.");
        if (outcome === "delivered") runtime.state = recovery.confirmed.state;
        recovery = undefined;
      });
    },
  };
}
