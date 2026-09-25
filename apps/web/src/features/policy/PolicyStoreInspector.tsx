import type { PolicySession } from "@rakazo/contracts";
import { APP2_DATALOG, formatFact } from "@rakazo/core";
import { Button } from "@rakazo/ui-web";
import { useEffect, useState } from "react";
import { rpc } from "../../lib/rpc";

const names: Record<string, string> = {
  global: "Global",
  board: "Board",
  procurement: "Procurement",
  facility: "Facility",
  hiring: "Hiring",
  auditor_a: "Auditor A",
};
const example = `// Add temporary facts and rules here.\nHasReason(A, C) :- Knows(A, nova, C).\n?- HasReason(A, C).`;
export function PolicyStoreInspector({ onClose }: { onClose: () => void }) {
  const [session, setSession] = useState<PolicySession | null>(null);
  const [error, setError] = useState("");
  const [scope, setScope] = useState("global");
  const [eventId, setEventId] = useState("latest");
  const [side, setSide] = useState<"before" | "after">("after");
  const [program, setProgram] = useState(example);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<
    { label: string; program: string; columns: string[]; rows: string[][]; error?: string }[]
  >([]);
  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const next = await rpc.policyNative.inspect({});
        if (active) {
          setSession(next);
          setError("");
        }
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : "Could not load stores.");
      }
    };
    void refresh();
    const timer = setInterval(() => void refresh(), 3000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);
  const event =
    eventId === "latest" ? undefined : session?.state.events.find((e) => String(e.seq) === eventId);
  const stores = event ? event[side] : eventId === "latest" ? session?.state.local : undefined;
  const entries = stores
    ? Object.entries(stores).filter(([id]) => scope === "global" || id === scope)
    : [];
  const grouped = new Map<string, { fact: string; owners: string[] }[]>();
  const merged = new Map<string, { predicate: string; fact: string; owners: string[] }>();
  for (const [owner, store] of entries)
    for (const f of store.facts) {
      const key = JSON.stringify(f);
      const row = merged.get(key) ?? { predicate: f.predicate, fact: formatFact(f), owners: [] };
      row.owners.push(owner);
      merged.set(key, row);
    }
  for (const row of merged.values())
    grouped.set(row.predicate, [...(grouped.get(row.predicate) ?? []), row]);
  const run = async () => {
    if (!session || !stores) return;
    setBusy(true);
    const label = `${names[scope]} · ${event ? `Event ${event.seq} · ${side}` : `Latest · revision ${session.revision}`}`;
    try {
      const result = await rpc.policyNative.query({
        revision: session.revision,
        event: event?.seq,
        side,
        scope,
        program,
      });
      setHistory((h) => [{ label, program, ...result }, ...h].slice(0, 20));
    } catch (e) {
      setHistory((h) =>
        [
          {
            label,
            program,
            columns: [],
            rows: [],
            error: e instanceof Error ? e.message : "Query failed.",
          },
          ...h,
        ].slice(0, 20),
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <aside
      aria-label="Store Inspector"
      className="absolute inset-y-0 right-0 z-40 flex w-full min-h-0 flex-col border-l border-border bg-background text-xs shadow-lg md:static md:w-[400px] md:shrink-0 md:shadow-none xl:w-[460px]"
    >
      <div className="flex items-center justify-between border-b border-border p-3">
        <strong>Store Inspector</strong>
        <Button size="sm" variant="ghost" onClick={onClose}>
          Close
        </Button>
      </div>
      <div className="grid grid-cols-2 gap-2 p-3">
        <label>
          Scope
          <select
            aria-label="Store scope"
            value={scope}
            onChange={(e) => setScope(e.target.value)}
            className="mt-1 w-full rounded border border-border bg-background p-2"
          >
            {Object.entries(names).map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label className="col-span-2 min-w-0">
          Message / event
          <select
            aria-label="Store snapshot"
            value={eventId}
            onChange={(e) => setEventId(e.target.value)}
            className="mt-1 w-full rounded border border-border bg-background p-2"
          >
            <option value="latest">Latest</option>
            {session?.state.events.map((e) => (
              <option key={e.seq} value={e.seq}>
                {`Event ${e.seq} · ${e.messageId ?? e.artifactId} · ${e.kind} · ${names[e.actor]}${e.decision ? ` · ${e.decision === "deny" ? "Denied" : "Delivered"}` : ""}`}
              </option>
            ))}
          </select>
        </label>
        {eventId !== "latest" && (
          <div className="col-span-2 flex gap-1">
            {(["before", "after"] as const).map((s) => (
              <Button
                key={s}
                size="sm"
                variant={side === s ? "secondary" : "ghost"}
                onClick={() => setSide(s)}
              >
                {s === "before" ? "Before" : "After"}
              </Button>
            ))}
          </div>
        )}
      </div>
      {event && (
        <div className="border-b border-border px-3 pb-3" data-testid="inspector-event">
          <code className="block break-all">{event.messageId ?? event.artifactId}</code>
          <p className="mt-1 text-muted-foreground">
            {event.from && event.to
              ? `${names[event.from]} → ${names[event.to]}`
              : names[event.actor]}
            {` · ${event.kind} · ${side === "before" ? "Before" : "After"}`}
          </p>
          <details className="mt-2">
            <summary className="cursor-pointer">Message / artifact</summary>
            <p className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap">
              {session?.state.artifacts[event.artifactId]?.text}
            </p>
          </details>
        </div>
      )}
      {error && (
        <p role="alert" className="px-3 text-destructive">
          {error}
        </p>
      )}
      <div className="min-h-0 flex-1 overflow-auto px-3 pb-3" data-testid="inspector-facts">
        {!stores && <p>Loading snapshot…</p>}
        {stores && !merged.size && <p className="text-muted-foreground">No facts</p>}
        {[...grouped.entries()]
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([predicate, rows]) => (
            <details key={predicate} open={predicate === "Knows"} className="mb-3">
              <summary className="cursor-pointer">
                {predicate} · {rows.length}
              </summary>
              {rows.map((row) => (
                <div key={row.fact} className="mt-1 rounded bg-muted p-2">
                  <code className="break-all">{row.fact}</code>
                  {scope === "global" && (
                    <div className="mt-1 text-muted-foreground">
                      {row.owners.map((id) => names[id]).join(", ")}
                    </div>
                  )}
                </div>
              ))}
            </details>
          ))}
        {event?.decision && (
          <p className="mb-2">
            {event.decision === "deny" ? `Denied · ${event.rules.join(", ")}` : "Delivered"}
          </p>
        )}
        <details className="mb-3">
          <summary className="cursor-pointer">Artifacts</summary>
          {[...new Set(entries.flatMap(([, store]) => store.artifacts))].map((id) => (
            <details key={id} className="mt-2">
              <summary className="cursor-pointer break-all">{id}</summary>
              <p className="mt-1 whitespace-pre-wrap">{session?.state.artifacts[id]?.text}</p>
            </details>
          ))}
        </details>
        {event?.decision === "deny" && (
          <details className="mb-3">
            <summary className="cursor-pointer">Rule witnesses</summary>
            {event.witnesses.map((f, i) => (
              <code key={i} className="mt-1 block break-all">
                {formatFact(f)}
              </code>
            ))}
          </details>
        )}
        <details>
          <summary className="cursor-pointer">Policy rules</summary>
          <pre className="mt-2 whitespace-pre-wrap break-all">{APP2_DATALOG}</pre>
        </details>
      </div>
      <section
        aria-label="Datalog Query"
        className="flex max-h-[60%] min-h-0 flex-col border-t border-border p-3"
      >
        <div className="mb-2 flex items-center justify-between">
          <strong>Datalog Query</strong>
          <Button size="sm" disabled={busy || !stores} onClick={() => void run()}>
            {busy ? "Running…" : "Run query"}
          </Button>
        </div>
        <textarea
          aria-label="Datalog program"
          value={program}
          onChange={(e) => setProgram(e.target.value)}
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
              e.preventDefault();
              if (!busy) void run();
            }
          }}
          spellCheck={false}
          className="min-h-28 shrink-0 resize-y rounded border border-border bg-background p-2 font-mono"
        />
        <details className="mt-2">
          <summary className="cursor-pointer text-muted-foreground">Syntax & scope</summary>
          <p className="mt-1">
            Read-only. Uppercase variables; lowercase or double-quoted constants. Use facts, rules
            with :-, recursion, not, !=, and one ?- query. End each statement with a period. _
            matches any value.
          </p>
          <p className="mt-1">
            Global combines local policy results. Store_Knows(Owner, A, P, C) and
            Store_Carries(Owner, M, P, C) preserve store ownership. Custom rules may join across
            stores. Temporary facts and rules never change enforcement. Incoming, New and Deny are
            transient gate facts, not stored facts.
          </p>
        </details>
        <div className="mt-2 min-h-0 overflow-auto" aria-live="polite">
          {history.map((result, i) => (
            <details key={i} open={i === 0} className="mb-3">
              <summary className="cursor-pointer">
                {result.label} · {result.error ? "Error" : `${result.rows.length} result(s)`}
              </summary>
              <pre className="my-2 whitespace-pre-wrap break-all text-muted-foreground">
                {result.program}
              </pre>
              {result.error ? (
                <p role="alert" className="text-destructive">
                  {result.error}
                </p>
              ) : result.columns.length ? (
                <table className="w-full text-left">
                  <thead>
                    <tr>
                      {result.columns.map((c) => (
                        <th key={c} className="border-b border-border p-1">
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.rows.map((row, n) => (
                      <tr key={n}>
                        {row.map((v, k) => (
                          <td key={k} className="break-all border-b border-border p-1">
                            {v}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p>{result.rows.length ? "True" : "False"}</p>
              )}
            </details>
          ))}
        </div>
      </section>
    </aside>
  );
}
