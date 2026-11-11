import { describe, expect, it, vi } from "vitest";
import { EffectNotAppliedError, EffectUncertainError } from "../src/application.js";
import { createBackendPort } from "../src/backend-port.js";
import type { PolicyFact } from "../src/datalog.js";
import { createMessagingProfile, createMessagingRuntime } from "../src/messaging.js";
import { parsePolicyRules } from "../src/query.js";

const f = (predicate: string, ...args: string[]): PolicyFact => ({ predicate, args });
const grants = [
  f("AgentHasCapability", "HR-Agent", "hr_review"),
  f("AgentHasCapability", "Reader-A", "hr_review"),
];
const profile = () =>
  createMessagingProfile({
    principals: ["SourceService", "HR-Agent", "Reader-A", "Reader-B"],
    sourceAuthorities: ["SourceService"],
    configuration: [f("TagRequiresCapability", "Hiring", "hr_review"), ...grants],
  });

describe("backend intervention and observation port", () => {
  it("installs application Datalog source against the declared backend contract", async () => {
    const p = createMessagingProfile({
      principals: ["writer", "reader"],
      sourceAuthorities: [],
      configuration: [f("BlockedRecipient", "reader")],
      application: {
        predicates: { BlockedRecipient: { kind: "input", args: ["Agent"] } },
        local: { BlockedRecipient: ["@self"] },
        rules: parsePolicyRules(
          "Deny(M, message_policy) :- ReceiveAttempt(A,M), BlockedRecipient(A).",
        ),
        ruleEncoding: "parsed",
      },
    });
    const deliver = vi.fn(async () => {});
    const port = createBackendPort({ profile: p, deliver });
    expect((await port.bind("writer").send("reader", "attempt", "plain")).allowed).toBe(false);
    expect(deliver).not.toHaveBeenCalled();
    expect(() => parsePolicyRules('MessageReceived("reader", "fake").')).toThrow(/facts/);
    expect(() => parsePolicyRules("?- Knows(A,T).")).toThrow();
  });
  it("preserves the snapshot on a failed send and protects primitive configuration", () => {
    const runtime = createMessagingRuntime(profile());
    const before = runtime.snapshot();
    expect(() =>
      runtime.send("SourceService", "HR-Agent", "m", "report", { tag: "x".repeat(1025) }),
    ).toThrow(/arity/);
    expect(runtime.snapshot()).toEqual(before);
    expect(() => runtime.configure([f("MessageReceived", "Reader-B", "fake")])).toThrow(/forge/);
    expect(runtime.snapshot()).toEqual(before);
    expect(() =>
      createMessagingProfile({
        principals: ["agent"],
        sourceAuthorities: [],
        configuration: [],
        application: {
          predicates: {},
          rules: [],
          local: { AgentHasCapability: ["_", "_"] },
        },
      }),
    ).toThrow(/primitive placement/);
    const remote = profile();
    remote.rules.push({
      id: "foreign-grant",
      head: f("Deny", "M", "message_policy"),
      body: [f("ReceiveAttempt", "A", "M"), f("AgentHasCapability", "B", "C")],
      distinct: [],
      stratum: 1,
    });
    expect(() => createMessagingRuntime(remote)).toThrow(/remote dependency/);
    const hidden = profile();
    hidden.predicates = {
      ...hidden.predicates,
      LocalKnowledge: { kind: "derived", args: ["Agent"] },
    };
    hidden.protocol.local = { ...hidden.protocol.local, LocalKnowledge: ["_"] };
    hidden.rules.push({
      id: "hidden-owner",
      head: f("LocalKnowledge", "A"),
      body: [f("Knows", "A", "T")],
      distinct: [],
      stratum: 1,
    });
    expect(() => createMessagingRuntime(hidden)).toThrow(/local ownership/);
  });
  for (const backend of ["inbox", "event-log"])
    it(`uses the same policy with an independent ${backend} backend`, async () => {
      const delivered: unknown[] = [];
      const port = createBackendPort({
        profile: profile(),
        deliver: async (m) => {
          delivered.push(backend === "inbox" ? m.body : { recipient: m.to, text: m.body });
        },
      });
      expect(
        (
          await port.ingest({
            authority: "SourceService",
            recipient: "HR-Agent",
            id: "0:source",
            body: "synthetic hiring report",
            tag: "Hiring",
          })
        ).allowed,
      ).toBe(true);
      const hr = port.bind("HR-Agent"),
        b = port.bind("Reader-B"),
        a = port.bind("Reader-A");
      expect((await hr.send("Reader-B", "1:blocked", "rewritten report")).allowed).toBe(false);
      expect(b.accessible()).toEqual([]);
      expect(b.query("?- Knows(A,T).").rows).toEqual([]);
      expect((await b.send("Reader-A", "2:plain", "ordinary output")).message.labels).toEqual([]);
      expect((await hr.send("Reader-A", "3:permitted", "summary")).allowed).toBe(true);
      expect(a.query("?- Knows(A,T).").rows).toEqual([["Reader-A", "Hiring"]]);
      expect(delivered).toHaveLength(3);
      expect(() => port.bind("intruder")).toThrow(/principal/);
      await expect(
        port.ingest({
          authority: "Reader-A",
          recipient: "Reader-B",
          id: "forged",
          body: "fake",
          tag: "Hiring",
        }),
      ).rejects.toThrow(/source authority/);
      expect(() => b.query('MessageReceived("Reader-B", "forged"). ?- Knows(A,T).')).toThrow(
        /read-only/,
      );
    });
  it("refreshes complete authoritative EDB and removes revoked grants before the next gate", async () => {
    let current = grants,
      version = "1",
      complete = true;
    const effect = vi.fn(async () => {});
    const port = createBackendPort({
      profile: profile(),
      deliver: effect,
      observations: [
        {
          id: "capability_authority",
          scope: "this_application",
          predicates: ["AgentHasCapability"],
          read: async () => ({ version, complete, facts: current }),
        },
      ],
    });
    await port.ingest({
      authority: "SourceService",
      recipient: "HR-Agent",
      id: "source",
      body: "report",
      tag: "Hiring",
    });
    current = grants.filter((f) => f.args[0] !== "Reader-A");
    version = "2";
    const result = await port.bind("HR-Agent").send("Reader-A", "after_revocation", "report");
    expect(result.allowed).toBe(false);
    expect(result.versions).toEqual({ capability_authority: "2" });
    expect(effect).toHaveBeenCalledTimes(1);
    complete = false;
    const before = port.snapshot();
    await expect(
      port.bind("HR-Agent").send("Reader-A", "unknown_evidence", "report"),
    ).rejects.toThrow(/Incomplete/);
    expect(port.snapshot()).toEqual(before);
  });
  it("rejects sources that forge runtime events or write undeclared input relations", async () => {
    expect(() =>
      createBackendPort({
        profile: profile(),
        deliver: async () => {},
        observations: [
          {
            id: "claims",
            scope: "app",
            predicates: ["MessageReceived"],
            read: async () => ({ version: "1", complete: true, facts: [] }),
          },
        ],
      }),
    ).toThrow(/forge runtime/);
    const port = createBackendPort({
      profile: profile(),
      deliver: async () => {},
      observations: [
        {
          id: "grants",
          scope: "app",
          predicates: ["AgentHasCapability"],
          read: async () => ({
            version: "1",
            complete: true,
            facts: [f("MessageReceived", "Reader-B", "fake")],
          }),
        },
      ],
    });
    await expect(port.bind("Reader-B").send("Reader-A", "m", "plain")).rejects.toThrow(
      /undeclared/,
    );
  });
  it("stops after uncertain delivery without retrying the external effect", async () => {
    const effect = vi.fn(async () => {
      throw new Error("Lost acknowledgement after external write.");
    });
    const port = createBackendPort({ profile: profile(), deliver: effect });
    await expect(port.bind("Reader-B").send("Reader-A", "m", "plain")).rejects.toBeInstanceOf(
      EffectUncertainError,
    );
    expect(port.snapshot().messages[0]!.status).toBe("pending");
    expect(
      port.snapshot().stores["Reader-A"]!.some((r) => r.fact.predicate === "MessageReceived"),
    ).toBe(false);
    await expect(port.bind("Reader-B").send("Reader-A", "m", "plain")).rejects.toBeInstanceOf(
      EffectUncertainError,
    );
    expect(effect).toHaveBeenCalledTimes(1);
    expect("reconcile" in port).toBe(false);
    expect(effect).toHaveBeenCalledTimes(1);
  });
  it("rechecks a pending attempt after a confirmed no-effect failure", async () => {
    const effect = vi
      .fn()
      .mockRejectedValueOnce(new EffectNotAppliedError("No write occurred."))
      .mockResolvedValue(undefined);
    const port = createBackendPort({ profile: profile(), deliver: effect });
    const sender = port.bind("Reader-B");
    await expect(sender.send("Reader-A", "m", "plain")).rejects.toBeInstanceOf(
      EffectNotAppliedError,
    );
    expect((await sender.send("Reader-A", "m", "plain")).allowed).toBe(true);
    expect(effect).toHaveBeenCalledTimes(2);
    await expect(sender.send("Reader-A", "m", "changed")).rejects.toThrow(/identity/);
  });
});
