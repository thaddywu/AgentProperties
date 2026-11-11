import type { PolicyFact, Rule } from "./datalog.js";
import { evaluateDatalog, factKey } from "./datalog.js";
import type { PlacementProtocol } from "./distributed.js";
import {
  acceptsFact,
  bindLocalRules,
  distributedClosure,
  validateRuleLocality,
} from "./distributed.js";
import { MESSAGING_PROTOCOL } from "./messaging-protocol.js";
import {
  MESSAGE_ROLES,
  PRIMITIVE_MESSAGING_RULES,
  PRIMITIVE_NAMES,
  PRIMITIVES,
} from "./primitives.js";
import {
  decode,
  encodeFact,
  encodeRule,
  limits,
  parseProgram,
  validateAndStratify,
} from "./query.js";
import { runSouffle } from "./souffle.js";

export type MessageInputRecord = {
  fact: PolicyFact;
  owner: string;
  source: "config" | "trusted app" | "runtime" | "analysis" | "protocol";
  event?: number;
  replicated?: boolean;
  lifetime: "global" | "local" | "temporary";
};
export type PolicyMessage = {
  id: string;
  from: string;
  to: string;
  body: string;
  status: "pending" | "delivered" | "denied";
  labels: PolicyFact[];
};
export type MessageStores = Record<string, MessageInputRecord[]>;
export type MessageEvent = {
  seq: number;
  kind: "send" | "receive" | "deny";
  message: string;
  actor: string;
  added: PolicyFact[];
  removed: PolicyFact[];
  before: MessageStores;
  after: MessageStores;
  check?: PolicyFact[];
  rule?: string;
};
export type MessagingState<Policy = unknown> = {
  policy?: Policy;
  stores: MessageStores;
  messages: PolicyMessage[];
  events: MessageEvent[];
  revision: number;
};
export type MessagingProtocol = PlacementProtocol & {
  temporary: readonly string[];
  transfers: {
    message: { export: string; import: string; messageArgument: number; retain: string };
  };
};
export type MessagingProfile = {
  principals: readonly string[];
  sourceAuthorities: readonly string[];
  predicates: Readonly<Record<string, { kind: string; args: readonly string[] }>>;
  protocol: MessagingProtocol;
  rules: Rule[];
  ruleEncoding: "raw" | "parsed";
  roles: { [K in keyof typeof MESSAGE_ROLES]: string };
  configuration: PolicyFact[];
  replicateAt?: Readonly<Record<string, readonly string[]>>;
  engine?: "typescript" | "souffle";
};
const f = (predicate: string, ...args: string[]): PolicyFact => ({ predicate, args });
const copy = <T>(value: T): T => structuredClone(value);
const records = (state: Pick<MessagingState, "stores">) => Object.values(state.stores).flat();
const recordKey = (record: MessageInputRecord) => `${record.owner}:${factKey(record.fact)}`;

export function messageInputRecord(
  profile: MessagingProfile,
  fact: PolicyFact,
  source: MessageInputRecord["source"],
  owner?: string,
): MessageInputRecord {
  const schema = profile.predicates[fact.predicate];
  if (
    schema?.kind !== "input" ||
    schema.args.length !== fact.args.length ||
    fact.args.some((arg) => typeof arg !== "string" || arg.length > 1024)
  )
    throw new Error(`Unknown input predicate or wrong arity: ${fact.predicate}`);
  const location =
    owner ?? (profile.protocol.replicated.includes(fact.predicate) ? "*" : fact.args[0]!);
  if (location !== "*" && !acceptsFact(profile.protocol, location, fact))
    throw new Error(`Protocol rejects ${fact.predicate} at ${location}`);
  return {
    fact,
    source,
    owner: location,
    lifetime: profile.protocol.temporary.includes(fact.predicate) ? "temporary" : "local",
  };
}
export function putMessageRecord(
  profile: MessagingProfile,
  state: Pick<MessagingState, "stores">,
  record: MessageInputRecord,
) {
  const broadcast = record.owner === "*";
  if (broadcast && !profile.protocol.replicated.includes(record.fact.predicate))
    throw new Error(`Predicate cannot be replicated: ${record.fact.predicate}`);
  const owners = broadcast
    ? (profile.replicateAt?.[record.fact.predicate] ?? profile.principals)
    : [record.owner];
  if (!owners.length) throw new Error("A configured relation needs an authoritative storage site.");
  for (const owner of owners) {
    const store = state.stores[owner];
    if (!store || !acceptsFact(profile.protocol, owner, record.fact))
      throw new Error(`Protocol rejects ${record.fact.predicate} at ${owner}`);
    const row = {
      ...copy(record),
      owner,
      lifetime: record.lifetime === "temporary" ? ("temporary" as const) : ("local" as const),
      ...(broadcast ? { replicated: true } : {}),
    };
    if (!store.some((r) => factKey(r.fact) === factKey(row.fact))) store.push(row);
  }
}

/** Backend-neutral message lifecycle. All policy decisions and knowledge come from Datalog. */
export class MessagingRuntime<
  Policy = unknown,
  State extends MessagingState<Policy> = MessagingState<Policy>,
> {
  readonly profile: MessagingProfile;
  private readonly rules: Rule[];
  state: State;
  constructor(profile: MessagingProfile, state: State) {
    this.profile = copy(profile);
    if (
      !profile.principals.length ||
      new Set(profile.principals).size !== profile.principals.length ||
      profile.principals.some((p) => typeof p !== "string" || !p.length || p.length > 1024) ||
      profile.sourceAuthorities.some((p) => !profile.principals.includes(p))
    )
      throw new Error("Messaging principals must be nonempty and unique.");
    this.rules = copy(
      profile.ruleEncoding === "raw" ? profile.rules.map(encodeRule) : profile.rules,
    );
    if (new Set(this.rules.map((rule) => rule.id)).size !== this.rules.length)
      throw new Error("Messaging rule identities must be unique.");
    for (const rule of this.rules) {
      for (const atom of [rule.head, ...rule.body]) {
        const schema = profile.predicates[atom.predicate];
        if (!schema || schema.args.length !== atom.args.length)
          throw new Error(`Unknown predicate or wrong arity: ${atom.predicate}`);
      }
      if (profile.predicates[rule.head.predicate]!.kind !== "derived")
        throw new Error("Rules cannot write input observations.");
    }
    validateAndStratify([], this.rules);
    validateRuleLocality(profile.protocol, this.rules);
    this.state = copy(state);
  }
  snapshot() {
    return copy(this.state);
  }
  private evaluate(input: PolicyFact[], rules: Rule[]) {
    if (this.profile.engine === "souffle") return runSouffle(input, rules);
    return {
      facts: evaluateDatalog(input.map(encodeFact), rules, limits).facts.map((fact) => ({
        ...fact,
        args: fact.args.map(decode),
      })),
    };
  }
  localInputs(owner: string) {
    if (!this.profile.principals.includes(owner)) throw new Error(`Unknown store: ${owner}`);
    const rows = this.state.stores[owner];
    if (!rows) throw new Error(`Missing local store: ${owner}`);
    for (const row of rows) {
      messageInputRecord(this.profile, row.fact, row.source, row.owner);
      if (row.owner !== owner || !acceptsFact(this.profile.protocol, owner, row.fact))
        throw new Error(`Misplaced fact in ${owner}: ${row.fact.predicate}`);
    }
    return rows.map((row) => row.fact);
  }
  closure(owner: string) {
    return this.evaluate(
      this.localInputs(owner),
      bindLocalRules(this.profile.protocol, this.rules, owner),
    );
  }
  inspect() {
    return distributedClosure(
      this.profile.protocol,
      this.rules,
      this.profile.principals,
      (owner) => this.localInputs(owner),
      (input, rules) => this.evaluate(input, rules),
    );
  }
  query(owner: string, source: string) {
    const parsed = parseProgram(source);
    if (parsed.facts.length || parsed.rules.length !== 1 || parsed.rules[0]!.id !== "query")
      throw new Error("Queries must be read-only.");
    for (const atom of parsed.rules[0]!.body) {
      const schema = this.profile.predicates[atom.predicate];
      if (!schema || schema.args.length !== atom.args.length)
        throw new Error("Unknown query predicate or wrong arity.");
    }
    validateAndStratify([], parsed.rules);
    const closed = owner === "observer" ? this.inspect().facts : this.closure(owner).facts;
    const result = this.evaluate(closed, parsed.rules);
    return {
      columns: parsed.columns,
      rows: result.facts.filter((f) => f.predicate === "QueryResult").map((f) => f.args),
    };
  }
  configure(config: PolicyFact[]) {
    const owned = new Set([
      this.profile.roles.sender,
      this.profile.roles.received,
      this.profile.roles.incoming,
      this.profile.roles.order,
      this.profile.roles.source,
      this.profile.roles.imported,
    ]);
    if (config.some((fact) => owned.has(fact.predicate)))
      throw new Error("Configuration cannot forge runtime events or source imports.");
    const next = { stores: copy(this.state.stores) };
    for (const owner of Object.keys(next.stores))
      next.stores[owner] = next.stores[owner]!.filter((r) => r.source !== "config");
    for (const fact of config)
      putMessageRecord(this.profile, next, messageInputRecord(this.profile, fact, "config"));
    this.state.stores = next.stores;
  }
  private append(record: MessageInputRecord) {
    putMessageRecord(this.profile, this.state, record);
  }
  private event(
    kind: MessageEvent["kind"],
    message: PolicyMessage,
    before: MessageStores,
    check?: PolicyFact[],
    rule?: string,
  ) {
    const after = records(this.state),
      beforeRows = Object.values(before).flat();
    const beforeKeys = new Set(beforeRows.map(recordKey)),
      afterKeys = new Set(after.map(recordKey));
    const seq = ++this.state.revision;
    for (const row of after) if (!beforeKeys.has(recordKey(row))) row.event = seq;
    this.state.events.push({
      seq,
      kind,
      message: message.id,
      actor: kind === "send" ? message.from : message.to,
      added: after.filter((r) => !beforeKeys.has(recordKey(r))).map((r) => r.fact),
      removed: beforeRows.filter((r) => !afterKeys.has(recordKey(r))).map((r) => r.fact),
      before,
      after: copy(this.state.stores),
      check,
      rule,
    });
  }
  send(from: string, to: string, id: string, body: string, trusted?: { tag: string }) {
    const before = this.snapshot();
    try {
      return this.stageSend(from, to, id, body, trusted);
    } catch (error) {
      this.state = before;
      throw error;
    }
  }
  private stageSend(from: string, to: string, id: string, body: string, trusted?: { tag: string }) {
    if (!this.profile.principals.includes(from) || !this.profile.principals.includes(to))
      throw new Error("Unknown sender or receiver.");
    if (
      typeof id !== "string" ||
      !id.length ||
      id.length > 1024 ||
      this.state.messages.some((m) => m.id === id)
    )
      throw new Error("Message ID must be a new bounded identifier.");
    if (typeof body !== "string" || !body.trim()) throw new Error("Message body is required.");
    if (trusted && !this.profile.sourceAuthorities.includes(from))
      throw new Error("Only a trusted source authority can attach a source tag.");
    const before = copy(this.state.stores),
      roles = this.profile.roles;
    this.append(messageInputRecord(this.profile, f(roles.sender, from, id), "runtime", from));
    if (trusted)
      this.append(
        messageInputRecord(this.profile, f(roles.source, id, trusted.tag), "trusted app", from),
      );
    if (!trusted)
      for (const row of before[from]!)
        if (row.fact.predicate === roles.received && row.fact.args[0] === from)
          this.append(
            messageInputRecord(
              this.profile,
              f(roles.order, row.fact.args[1]!, id),
              "runtime",
              from,
            ),
          );
    this.append(messageInputRecord(this.profile, f(roles.incoming, to, id), "runtime", to));
    const transfer = this.profile.protocol.transfers.message;
    const labels = this.closure(from).facts.filter(
      (fact) => fact.predicate === transfer.export && fact.args[transfer.messageArgument] === id,
    );
    const message: PolicyMessage = { id, from, to, body, labels, status: "pending" };
    this.state.messages.push(message);
    for (const label of labels) {
      const row = messageInputRecord(
        this.profile,
        f(transfer.import, ...label.args),
        "protocol",
        to,
      );
      row.lifetime = "temporary";
      this.append(row);
    }
    this.event("send", message, before);
    return copy(message);
  }
  settle(id: string) {
    const message = this.state.messages.find((m) => m.id === id);
    if (message?.status !== "pending") throw new Error("Select a pending message.");
    const roles = this.profile.roles,
      imported = this.profile.protocol.transfers.message.import;
    const local = this.localInputs(message.to);
    if (
      !local.some(
        (f) => factKey(f) === factKey({ predicate: roles.incoming, args: [message.to, id] }),
      )
    )
      throw new Error(`Missing local receive intent for ${id}; delivery was not attempted.`);
    for (const label of message.labels)
      if (!local.some((f) => factKey(f) === factKey({ predicate: imported, args: label.args })))
        throw new Error(`Incomplete tag envelope for ${id}; delivery was not attempted.`);
    const before = copy(this.state.stores),
      evaluation = this.closure(message.to);
    const denied = evaluation.facts.some((f) => f.predicate === roles.deny && f.args[0] === id);
    this.state.stores[message.to] = this.state.stores[message.to]!.filter(
      (r) => factKey(r.fact) !== factKey({ predicate: roles.incoming, args: [message.to, id] }),
    );
    if (!denied)
      this.append(
        messageInputRecord(this.profile, f(roles.received, message.to, id), "runtime", message.to),
      );
    this.state.stores[message.to] = this.state.stores[message.to]!.filter((row) => {
      if (row.fact.predicate !== imported || row.fact.args[0] !== id) return true;
      if (denied) return false;
      row.lifetime = "local";
      return true;
    });
    message.status = denied ? "denied" : "delivered";
    this.event(
      denied ? "deny" : "receive",
      message,
      before,
      evaluation.facts,
      denied
        ? `${this.profile.engine === "souffle" ? "Soufflé" : "Datalog"}: ${roles.deny}`
        : undefined,
    );
    return { allowed: !denied, evaluation, message: copy(message) };
  }
  accessible(principal: string) {
    return this.state.messages
      .filter((m) => m.from === principal || (m.to === principal && m.status === "delivered"))
      .map(copy);
  }
}

export function createMessagingProfile(options: {
  principals: string[];
  sourceAuthorities: string[];
  configuration: PolicyFact[];
  application?: {
    predicates: Record<string, { kind: string; args: string[] }>;
    rules: Rule[];
    local: Record<string, string[]>;
    replicated?: string[];
    observer?: string[];
    ruleEncoding?: "raw" | "parsed";
  };
}): MessagingProfile {
  const app = options.application;
  for (const name of Object.keys(app?.predicates ?? {}))
    if (Object.hasOwn(PRIMITIVES, name))
      throw new Error(`Application cannot redefine primitive ${name}.`);
  for (const name of [
    ...Object.keys(app?.local ?? {}),
    ...(app?.replicated ?? []),
    ...(app?.observer ?? []),
  ])
    if (Object.hasOwn(PRIMITIVES, name))
      throw new Error(`Application cannot replace primitive placement: ${name}.`);
  const name = (legacy: string) =>
    PRIMITIVE_NAMES[legacy as keyof typeof PRIMITIVE_NAMES] ?? legacy;
  const predicates = Object.fromEntries(
    Object.entries(PRIMITIVES).filter(([predicate]) =>
      Object.values(PRIMITIVE_NAMES).some((p) => p === predicate),
    ),
  );
  for (const rule of app?.rules ?? []) {
    if (
      Object.hasOwn(predicates, rule.head.predicate) &&
      rule.head.predicate !== MESSAGE_ROLES.deny
    )
      throw new Error("Application cannot replace the messaging foundation.");
  }
  return {
    principals: options.principals,
    sourceAuthorities: options.sourceAuthorities,
    configuration: options.configuration,
    predicates: { ...predicates, ...app?.predicates },
    rules:
      app?.ruleEncoding === "parsed"
        ? [...PRIMITIVE_MESSAGING_RULES.map(encodeRule), ...app.rules]
        : [...PRIMITIVE_MESSAGING_RULES, ...(app?.rules ?? [])],
    ruleEncoding: app?.ruleEncoding === "parsed" ? "parsed" : "raw",
    roles: MESSAGE_ROLES,
    protocol: {
      replicated: [...MESSAGING_PROTOCOL.replicated.map(name), ...(app?.replicated ?? [])],
      local: {
        ...Object.fromEntries(
          Object.entries(MESSAGING_PROTOCOL.local).map(([p, pattern]) => [name(p), pattern]),
        ),
        ...app?.local,
      },
      onlyAt:
        options.sourceAuthorities.length === 1 ? { SourceTag: options.sourceAuthorities[0]! } : {},
      observer: app?.observer ?? [],
      temporary: MESSAGING_PROTOCOL.temporary.map(name),
      transfers: {
        message: {
          ...MESSAGING_PROTOCOL.message,
          export: name(MESSAGING_PROTOCOL.message.export),
          import: name(MESSAGING_PROTOCOL.message.import),
        },
      },
    },
  };
}
export function createMessagingRuntime(profile: MessagingProfile) {
  const state: MessagingState = {
    stores: Object.fromEntries(profile.principals.map((p) => [p, []])),
    messages: [],
    events: [],
    revision: 0,
  };
  const runtime = new MessagingRuntime(profile, state);
  runtime.configure(profile.configuration);
  return runtime;
}
