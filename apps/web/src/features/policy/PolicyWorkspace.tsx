import type { PolicyEvent, PolicyFact, PolicyPrincipal, PolicySession } from "@rakazo/contracts";
import { APP2_DATALOG, formatFact, NOVA_PHASES, NOVA_PRINCIPALS } from "@rakazo/core";
import { Button, Dialog, DialogContent, DialogTitle, Switch } from "@rakazo/ui-web";
import {
  ArrowLeft,
  ArrowRight,
  Database,
  FileCode2,
  Pause,
  Play,
  ShieldCheck,
  X,
} from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { setUiLocale } from "../../lib/i18n";
import { rpc, selectedSpaceId } from "../../lib/rpc";
import "./policy.css";

const names: Record<PolicyPrincipal, string> = {
  board: "Executive Board",
  procurement: "Procurement",
  facility: "Facility",
  hiring: "Hiring",
  auditor_a: "Auditor A",
};
const showFacts = (facts: PolicyFact[]) =>
  facts.length ? (
    <ul className="policy-facts">
      {facts.map((f, i) => (
        <li key={`${formatFact(f)}-${i}`}>
          <code>{formatFact(f)}.</code>
        </li>
      ))}
    </ul>
  ) : (
    <span className="text-xs text-muted-foreground">None</span>
  );
export function PolicyWorkspace({ children, userId }: { children: ReactNode; userId: string }) {
  const key = `rakazo:policy:${userId}:${selectedSpaceId() ?? "default"}`;
  const [enabled, setEnabled] = useState(() => {
    try {
      return localStorage.getItem(key) === "on";
    } catch {
      return false;
    }
  });
  const [visited, setVisited] = useState(enabled);
  useEffect(() => {
    void setUiLocale("en");
  }, []);
  const toggle = (value: boolean) => {
    setEnabled(value);
    setVisited(true);
    try {
      localStorage.setItem(key, value ? "on" : "off");
    } catch {}
  };
  return (
    <div className="flex h-full flex-col">
      <header className="flex h-12 shrink-0 items-center gap-3 border-b border-border bg-background px-4">
        <ShieldCheck className="size-4" />
        <label htmlFor="policy-switch" className="text-xs font-medium">
          Use Our Policy
        </label>
        <Switch
          id="policy-switch"
          aria-label="Use Our Policy"
          checked={enabled}
          onCheckedChange={toggle}
        />
        {enabled && (
          <span className="text-xs text-muted-foreground">
            Isolated session · enforced by runtime
          </span>
        )}
      </header>
      <div className="min-h-0 flex-1" style={{ display: enabled ? "none" : "block" }}>
        {children}
      </div>
      {visited && (
        <div className="min-h-0 flex-1" style={{ display: enabled ? "block" : "none" }}>
          <PolicyConsole key={key} active={enabled} />
        </div>
      )}
    </div>
  );
}
function PolicyConsole({ active }: { active: boolean }) {
  const [session, setSession] = useState<PolicySession | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [cursor, setCursor] = useState<number | null>(null);
  const [principal, setPrincipal] = useState<PolicyPrincipal>("auditor_a");
  const [side, setSide] = useState<"before" | "after">("after");
  const [protocolOpen, setProtocolOpen] = useState(false);
  const [mobileStore, setMobileStore] = useState(false);
  const runningRef = useRef(false);
  const inFlight = useRef(false);
  const selectedRef = useRef<HTMLElement>(null);
  useEffect(() => {
    let live = true;
    void rpc.policySessions
      .get({})
      .then((s) => {
        if (live) {
          setSession(s);
          setLoaded(true);
        }
      })
      .catch(() => {
        if (live) {
          setLoaded(true);
          setError("Could not load the policy session.");
        }
      });
    return () => {
      live = false;
    };
  }, []);
  useEffect(() => {
    if (!active) {
      runningRef.current = false;
      setRunning(false);
    }
  }, [active]);
  const advance = async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      const next = session
        ? await rpc.policySessions.advance({ id: session.id, revision: session.revision })
        : await rpc.policySessions.create({});
      setSession(next);
      setCursor(null);
      if (next.state.phase >= NOVA_PHASES.length) {
        runningRef.current = false;
        setRunning(false);
      }
    } catch (err) {
      runningRef.current = false;
      setRunning(false);
      setError(
        err instanceof Error ? err.message : "Step failed. Retry without changing the local state.",
      );
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };
  useEffect(() => {
    if (running && active && !busy && runningRef.current) void advance();
  }, [running, active, busy, session]);
  const events = session?.state.events ?? [];
  const event = events[cursor ?? events.length - 1];
  useEffect(() => {
    if (active) selectedRef.current?.scrollIntoView({ block: "nearest" });
  }, [event?.seq, active]);
  const store = event?.[side][principal] ?? session?.state.local[principal];
  const delta =
    event?.after[principal].facts.filter(
      (f) => !event.before[principal].facts.some((old) => formatFact(old) === formatFact(f)),
    ) ?? [];
  const inspect = (e: PolicyEvent) => {
    setCursor(e.seq - 1);
    setPrincipal(e.actor);
  };
  return (
    <div className="policy-layout" data-testid="policy-console">
      <aside className="policy-agents">
        <div className="mb-8">
          <h1 className="text-sm font-semibold">Nova Budget Audit</h1>
          <p className="mt-1 text-xs text-muted-foreground">App 2 · No sanitization</p>
        </div>
        <div className="mb-3 text-[10px] uppercase tracking-widest text-muted-foreground">
          Principals
        </div>
        {NOVA_PRINCIPALS.map((id) => (
          <button
            type="button"
            key={id}
            className={`policy-agent ${principal === id ? "bg-muted" : ""}`}
            onClick={() => {
              setPrincipal(id);
              setMobileStore(true);
            }}
          >
            <Database className="size-4" />
            <span>
              {names[id]}
              <small>
                {id === "board"
                  ? "Receive exemption"
                  : `${(event?.after ?? session?.state.local)?.[id].facts.filter((f) => f.predicate === "Knows").length ?? 0} restricted components`}
              </small>
            </span>
          </button>
        ))}
        <Button
          variant="ghost"
          className="mt-auto justify-start"
          onClick={() => setProtocolOpen(true)}
        >
          <FileCode2 />
          Protocol & rules
        </Button>
      </aside>
      <main className="policy-stream">
        <div className="policy-heading">
          <div>
            <div className="mb-2 text-[10px] uppercase tracking-widest text-muted-foreground">
              Live protocol execution
            </div>
            <h2 className="text-xl font-semibold">Trace every delivery.</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Runtime facts, model-generated replies, receiver-side enforcement.
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Open local store"
            onClick={() => setMobileStore(true)}
          >
            <Database />
          </Button>
        </div>
        <div className="policy-controls">
          <Button
            disabled={!loaded || (busy && !running) || session?.state.phase === NOVA_PHASES.length}
            onClick={() => {
              if (running) {
                runningRef.current = false;
                setRunning(false);
              } else {
                runningRef.current = true;
                setRunning(true);
              }
            }}
          >
            {running ? <Pause /> : <Play />}
            {running ? "Pause after step" : "Run episode"}
          </Button>
          {session?.state.phase === NOVA_PHASES.length && (
            <Button
              variant="outline"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  setSession(await rpc.policySessions.create({}));
                  setCursor(null);
                  setError("");
                } catch {
                  setError("Could not create a new session.");
                } finally {
                  setBusy(false);
                }
              }}
            >
              New session
            </Button>
          )}
          <Button
            variant="outline"
            disabled={!loaded || busy || running || session?.state.phase === NOVA_PHASES.length}
            onClick={() => void advance()}
          >
            Next step
          </Button>
          <span className="ml-auto text-xs text-muted-foreground">
            {busy
              ? "Executing…"
              : session?.state.phase === NOVA_PHASES.length
                ? "Finished"
                : NOVA_PHASES[session?.state.phase ?? 0]}
          </span>
        </div>
        {error && (
          <div
            role="alert"
            className="mx-6 mt-3 rounded-lg border border-destructive p-3 text-sm text-destructive"
          >
            {error}
          </div>
        )}
        <div className="policy-events">
          {!events.length && (
            <div className="policy-empty">
              <ShieldCheck className="mb-4 size-8 text-muted-foreground" />
              <h3 className="font-semibold">Ready to enforce App 2</h3>
              <p className="mt-2 max-w-sm text-sm leading-relaxed text-muted-foreground">
                Board distributes budgets and restricted reasons. Department replies inherit their
                accessible history. A third distinct component is denied before delivery.
              </p>
              <p className="mt-4 text-xs text-muted-foreground">
                Uses your connected default model. Each step is saved.
              </p>
            </div>
          )}
          {events.map((e) => {
            const artifact = session!.state.artifacts[e.artifactId]!;
            return (
              <article
                key={e.seq}
                ref={e.seq === event?.seq ? selectedRef : undefined}
                className={`policy-event ${e.seq === event?.seq ? "policy-selected" : ""} ${e.decision === "deny" ? "policy-denied" : ""}`}
                data-testid={`event-${e.seq}`}
              >
                <button type="button" className="policy-event-top" onClick={() => inspect(e)}>
                  <span>
                    {String(e.seq).padStart(2, "0")} · {e.kind.toUpperCase()}
                  </span>
                  <span>
                    {e.decision === "deny"
                      ? "Denied"
                      : e.decision === "allow"
                        ? "Allowed"
                        : "Inspect"}{" "}
                    <ArrowRight className="inline size-3" />
                  </span>
                </button>
                <div className="policy-event-body">
                  <div>
                    <div className="mb-2 text-sm font-semibold">
                      {e.from && e.to ? `${names[e.from]} → ${names[e.to]}` : names[e.actor]}
                    </div>
                    {e.messageId && <code className="policy-id">{e.messageId}</code>}
                    {e.decision === "deny" && (
                      <p className="mb-2 text-xs text-destructive">
                        Observer only · payload never delivered
                      </p>
                    )}
                    <p className="text-[13px] leading-relaxed">{artifact.text}</p>
                    {e.kind === "compute" && (
                      <p className="mt-3 text-[10px] text-muted-foreground">
                        {e.model} · {artifact.inputs.length} runtime-recorded inputs
                      </p>
                    )}
                  </div>
                  <div className="policy-attached">
                    <div className="mb-3 text-[10px] uppercase tracking-wider text-muted-foreground">
                      Attached facts · {artifact.carries.length}
                    </div>
                    {showFacts(
                      artifact.carries.map((label) => ({
                        predicate: "Carries",
                        args: [artifact.id, label.project, label.component],
                      })),
                    )}
                  </div>
                </div>
                {e.decision === "deny" && (
                  <div className="policy-deny-note">
                    {e.rules.join(", ")} · Receiver store unchanged
                  </div>
                )}
              </article>
            );
          })}
          {session?.state.phase === NOVA_PHASES.length && (
            <div className="rounded-xl bg-muted p-5">
              <h3 className="font-semibold">
                {session.state.status === "blocked"
                  ? "Audit incomplete — policy enforced"
                  : "Audit completed"}
              </h3>
              <p className="mt-2 text-xs text-muted-foreground">
                The result above was generated from delivered inputs only. No sanitized or
                declassified messages exist.
              </p>
            </div>
          )}
        </div>
        <footer className="policy-timeline">
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label="Previous event"
            disabled={!event || event.seq <= 1}
            onClick={() => setCursor(event!.seq - 2)}
          >
            <ArrowLeft />
          </Button>
          <input
            aria-label="Event timeline"
            type="range"
            min={0}
            max={Math.max(0, events.length - 1)}
            value={event ? event.seq - 1 : 0}
            disabled={!events.length}
            onChange={(e) => setCursor(Number(e.target.value))}
          />
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label="Next event"
            disabled={!event || event.seq === events.length}
            onClick={() => setCursor(event!.seq)}
          >
            <ArrowRight />
          </Button>
          <span className="text-xs tabular-nums">
            {event?.seq ?? 0} / {events.length}
          </span>
          <Button variant="ghost" size="sm" onClick={() => setCursor(null)}>
            Latest
          </Button>
        </footer>
      </main>
      {mobileStore && (
        <button
          type="button"
          className="policy-store-shade"
          aria-label="Close inspector"
          onClick={() => setMobileStore(false)}
        />
      )}
      <aside className={`policy-store ${mobileStore ? "policy-store-open" : ""}`}>
        <header className="mb-5 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Local store</h2>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Close local store"
            onClick={() => setMobileStore(false)}
          >
            <X />
          </Button>
        </header>
        <select
          aria-label="Principal"
          className="policy-select"
          value={principal}
          onChange={(e) => setPrincipal(e.target.value as PolicyPrincipal)}
        >
          {NOVA_PRINCIPALS.map((id) => (
            <option key={id} value={id}>
              {names[id]}
            </option>
          ))}
        </select>
        <div className="my-4 flex items-center justify-between text-xs">
          <span>Event {event?.seq ?? 0}</span>
          <div>
            {(["before", "after"] as const).map((value) => (
              <Button
                variant={side === value ? "secondary" : "ghost"}
                size="sm"
                key={value}
                onClick={() => setSide(value)}
              >
                {value === "before" ? "Before" : "After"}
              </Button>
            ))}
          </div>
        </div>
        <div data-testid="local-facts">
          {["Knows", "Received", "Carries", "DerivedFrom"].map((predicate) => (
            <details
              key={`${principal}-${predicate}`}
              open={predicate === "Knows" || predicate === "Received"}
              className="mb-4"
            >
              <summary className="mb-2 cursor-pointer text-xs font-semibold">
                {predicate} · {store?.facts.filter((f) => f.predicate === predicate).length ?? 0}
              </summary>
              {showFacts(store?.facts.filter((f) => f.predicate === predicate) ?? [])}
            </details>
          ))}
        </div>
        <div className="policy-section">
          <h3>Accessible artifacts · {store?.artifacts.length ?? 0}</h3>
          {store?.artifacts.map((id) => (
            <details key={id} className="mb-3 text-xs">
              <summary className="cursor-pointer">
                <code>{id}</code>
              </summary>
              <p className="mt-2 leading-relaxed">{session?.state.artifacts[id]?.text}</p>
            </details>
          ))}
        </div>
        <div className="policy-section">
          <h3>Added at this event</h3>
          {showFacts(delta)}
        </div>
        {event?.decision && (
          <div className="policy-section" data-testid="policy-decision">
            <h3 className={event.decision === "deny" ? "text-destructive" : ""}>
              Receive {event.decision === "deny" ? "denied" : "allowed"}
            </h3>
            <p className="mb-3 text-xs">
              {event.rules.join(", ") ||
                (event.actor === "board" ? "Board exemption" : "No denial rule matched")}
            </p>
            <h3>Ephemeral evaluation context</h3>
            {showFacts(event.incoming)}
            <h3 className="mt-4">Rule witnesses</h3>
            {showFacts(event.witnesses)}
            <p className="mt-3 text-xs text-muted-foreground">
              Incoming, New and Deny are discarded.{" "}
              {event.decision === "deny"
                ? "No Received or Knows was added."
                : "Received and local closure commit together."}
            </p>
          </div>
        )}
        {event && session && session.state.artifacts[event.artifactId]!.inputs.length > 0 && (
          <div className="policy-section">
            <h3>Computation dependencies</h3>
            {showFacts(
              session.state.artifacts[event.artifactId]!.inputs.map((id) => ({
                predicate: "DerivedFrom",
                args: [event.artifactId, id],
              })),
            )}
          </div>
        )}
        <p className="mt-6 text-[11px] text-muted-foreground">
          Observer state is never included in agent inputs.
        </p>
      </aside>
      <Dialog open={protocolOpen} onOpenChange={setProtocolOpen}>
        <DialogContent className="max-h-[85vh] overflow-auto sm:max-w-3xl">
          <DialogTitle>App 2 · Protocol & rules</DialogTitle>
          <div className="space-y-3 text-sm leading-relaxed">
            <p>
              <strong>Create:</strong> trusted Board initialization annotates source artifacts with
              Carries. Models cannot supply or remove policy facts.
            </p>
            <p>
              <strong>Compute:</strong> the runtime passes every locally accessible artifact to the
              model and records DerivedFrom for exactly those inputs. Datalog derives output
              Carries.
            </p>
            <p>
              <strong>Send:</strong> only payload and its Carries travel. Artifact identity is
              immutable; message numbers share an unordered pair counter.
            </p>
            <p>
              <strong>Receive:</strong> evaluate local state plus Incoming and transported Carries
              under a database lock. Deny creates only an observer audit event. Allow adds the
              artifact and Received, then derives Knows. Temporary facts are discarded.
            </p>
            <p>
              <strong>Isolation:</strong> these agents have no shared files, native chat history,
              external tools or global memory. Original Rakazo sessions are separate. No
              sanitization.
            </p>
            <pre className="overflow-x-auto rounded-lg bg-muted p-4 text-xs">{APP2_DATALOG}</pre>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
