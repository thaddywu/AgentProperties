import type { NovaView, Request, Selection } from "@rakazo/core/policy/reasoning/service";
import { NAMES, PRINCIPALS } from "@rakazo/core/policy/reasoning/shared";
import { BotAvatar, Button, Dialog, DialogContent, DialogTitle } from "@rakazo/ui-web";
import {
  ArrowRight,
  Database,
  FileCode2,
  MessageSquare,
  PanelRightClose,
  PanelRightOpen,
  Play,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useState } from "react";
import { AnalysisTerminal } from "./AnalysisTerminal";
import { request } from "./client";

const format = (f: { predicate: string; args: string[] }) => `${f.predicate}(${f.args.join(", ")})`;
const control = "rounded border border-border bg-background px-2 py-1.5 text-xs";
export function NovaApp() {
  const [state, setState] = useState<NovaView | null>(null);
  const [selection, setSelection] = useState<Selection>({});
  const [scope, setScope] = useState("auditor_a");
  const [principal, setPrincipal] = useState("all");
  const [open, setOpen] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [rules, setRules] = useState(false);
  const [protocolOpen, setProtocolOpen] = useState(false);
  const [configOpen, setConfigOpen] = useState(false);
  const [config, setConfig] = useState("");
  const [sender, setSender] = useState("hr");
  const [receiver, setReceiver] = useState("auditor_a");
  const [body, setBody] = useState("");
  useEffect(() => {
    let active = true;
    request<NovaView>({ operation: "state", ...selection })
      .then((s) => {
        if (active) {
          setState(s);
          setError("");
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [selection]);
  const mutate = async (req: Request) => {
    if (!state) return;
    setBusy(true);
    setError("");
    try {
      const next = await request<NovaView>({ ...req, revision: state.version });
      setState(next);
      setSelection({});
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  };
  const messages =
    state?.messages.filter(
      (m) => principal === "all" || m.from === principal || m.to === principal,
    ) ?? [];
  return (
    <main className="flex h-full flex-col bg-background text-foreground">
      <header className="flex min-h-12 shrink-0 flex-wrap items-center gap-3 border-b border-border px-4 py-2">
        <ShieldCheck className="size-4" />
        <strong className="text-sm">Nova</strong>
        <span className="text-xs text-muted-foreground">Distributed Policy Reasoning</span>
        <span className="ml-auto hidden text-xs text-muted-foreground sm:inline">
          Local runtime · Datalog
        </span>
        <Button size="sm" variant="ghost" onClick={() => setRules(true)}>
          <FileCode2 className="size-3.5" />
          Rules
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setProtocolOpen(true)}>
          Protocol
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            setConfig(state?.configuration.map((fact) => `${format(fact)}.`).join("\n") ?? "");
            setConfigOpen(true);
          }}
        >
          Config
        </Button>
        <Button
          size="sm"
          variant="ghost"
          aria-label="Toggle Store Inspector"
          onClick={() => setOpen((v) => !v)}
        >
          {open ? <PanelRightClose className="size-4" /> : <PanelRightOpen className="size-4" />}
        </Button>
      </header>
      {error && (
        <div role="alert" className="border-b border-border p-3 text-sm text-destructive">
          {error}
        </div>
      )}
      <div className="relative flex min-h-0 flex-1">
        <nav
          aria-label="Principals"
          className="hidden w-48 shrink-0 border-r border-border bg-muted/20 p-3 lg:block"
        >
          <p className="mb-3 text-xs text-muted-foreground">Nova workspace</p>
          <button
            type="button"
            onClick={() => setPrincipal("all")}
            className={`mb-2 flex w-full items-center gap-2 rounded p-2 text-left text-xs ${principal === "all" ? "bg-muted" : ""}`}
          >
            <MessageSquare className="size-4" />
            All messages
          </button>
          {PRINCIPALS.map((id) => (
            <button
              type="button"
              key={id}
              onClick={() => {
                setPrincipal(id);
                setSender(id);
              }}
              className={`mb-1 flex w-full items-center gap-2 rounded p-2 text-left text-xs ${principal === id ? "bg-muted" : ""}`}
            >
              <BotAvatar identity={id} color="slate" size={26} />
              <span>{NAMES[id]}</span>
            </button>
          ))}
          <div className="mt-6 space-y-2 border-t border-border pt-3 text-xs text-muted-foreground">
            <p>{state?.messages.length ?? 0} messages</p>
            <p>{state?.liveEvents.length ?? 0} runtime events</p>
            <p>{state?.finished ? "Audit complete" : "Audit incomplete"}</p>
          </div>
        </nav>
        <section aria-label="Runtime messages" className="flex min-w-0 flex-1 flex-col">
          <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-border p-3">
            <div className="mr-auto">
              <h1 className="text-sm font-medium">
                {principal === "all" ? "Nova budget audit" : NAMES[principal]}
              </h1>
              <p className="mt-1 text-xs text-muted-foreground">
                {selection.event
                  ? `Event ${selection.event} · ${selection.side}`
                  : "Current runtime"}
              </p>
            </div>
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => void mutate({ operation: "reset", preset: "initial" })}
            >
              <RotateCcw className="size-3" />
              New
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => void mutate({ operation: "reset", preset: "earlier" })}
            >
              Earlier
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => void mutate({ operation: "reset", preset: "denial" })}
            >
              Denial
            </Button>
            <Button
              size="sm"
              disabled={busy || !!selection.event}
              onClick={() => void mutate({ operation: "advance" })}
            >
              <Play className="size-3" />
              Next event
            </Button>
          </div>
          <div className="min-h-0 flex-1 overflow-auto p-4 sm:p-6">
            {!state && <p className="text-sm text-muted-foreground">Loading runtime…</p>}
            {state && !messages.length && (
              <div className="mx-auto max-w-lg rounded border border-border p-5 text-sm">
                <p>Ready to launch Nova.</p>
                <p className="mt-2 text-muted-foreground">
                  Advance the runtime to send the Board assignments, deliver them, and collect the
                  department replies.
                </p>
              </div>
            )}
            <div className="mx-auto max-w-2xl space-y-5">
              {messages.map((message) => {
                const denial = state?.derived.find(
                  (r) =>
                    r.fact.predicate === "DenyReceive" &&
                    r.fact.args[0] === message.to &&
                    r.fact.args[1] === message.id,
                );
                return (
                  <article
                    key={message.id}
                    data-testid={`message-${message.id}`}
                    className="rounded-lg border border-border bg-background p-4"
                  >
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <BotAvatar identity={message.from} color="slate" size={26} />
                      <strong>{NAMES[message.from]}</strong>
                      <ArrowRight className="size-3 text-muted-foreground" />
                      <span>{NAMES[message.to]}</span>
                      <code className="ml-auto text-muted-foreground">{message.id}</code>
                    </div>
                    <p className="my-3 whitespace-pre-wrap text-sm leading-relaxed">
                      {message.body}
                    </p>
                    <div className="space-y-1 text-xs text-muted-foreground">
                      {message.labels.map((label) => (
                        <code key={format(label)} className="block break-all">
                          {format(label)}
                        </code>
                      ))}
                    </div>
                    <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border pt-2 text-xs">
                      <span
                        className={
                          message.status === "denied" || denial
                            ? "text-destructive"
                            : "text-muted-foreground"
                        }
                      >
                        {message.status === "pending"
                          ? denial
                            ? `Pending · would deny (${denial.rule})`
                            : "Pending policy check"
                          : message.status === "denied"
                            ? "Denied · recipient did not receive this payload"
                            : "Delivered"}
                      </span>
                      {message.status === "pending" && !selection.event && (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={busy}
                          onClick={() => void mutate({ operation: "settle", id: message.id })}
                        >
                          Check & deliver
                        </Button>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
          </div>
          <form
            className="shrink-0 space-y-2 border-t border-border p-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (!body.trim() || !state) return;
              void mutate({
                operation: "send",
                from: sender,
                to: receiver,
                id: `msg_${state.version}_${state.messages.length + 1}`,
                body,
              }).then(() => setBody(""));
            }}
          >
            <div className="flex flex-wrap items-center gap-2">
              <label className="text-xs">
                From{" "}
                <select
                  aria-label="Message sender"
                  className={control}
                  value={sender}
                  onChange={(e) => setSender(e.target.value)}
                >
                  {PRINCIPALS.map((p) => (
                    <option key={p} value={p}>
                      {NAMES[p]}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-xs">
                To{" "}
                <select
                  aria-label="Message receiver"
                  className={control}
                  value={receiver}
                  onChange={(e) => setReceiver(e.target.value)}
                >
                  {PRINCIPALS.map((p) => (
                    <option key={p} value={p}>
                      {NAMES[p]}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="flex items-end gap-2">
              <textarea
                aria-label="Message body"
                value={body}
                onChange={(e) => setBody(e.target.value)}
                rows={2}
                placeholder="Send a message through the policy runtime…"
                className="min-w-0 flex-1 resize-y rounded border border-border bg-background p-2 text-sm"
              />
              <Button
                type="submit"
                size="sm"
                disabled={busy || !state || !!selection.event || !body.trim()}
              >
                Send
              </Button>
            </div>
          </form>
        </section>
        {open && state && (
          <aside
            aria-label="Store Inspector"
            className="absolute inset-y-0 right-0 z-20 flex w-full min-h-0 flex-col border-l border-border bg-background shadow-lg md:static md:w-[460px] md:shrink-0 md:shadow-none xl:w-[560px]"
          >
            <div className="flex shrink-0 items-center gap-2 border-b border-border p-3">
              <Database className="size-4" />
              <strong className="text-xs">Store Inspector</strong>
              <span className="ml-auto text-xs text-muted-foreground">
                revision {state.version}
              </span>
              <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
                Close
              </Button>
            </div>
            <div className="flex h-[42%] min-h-36 shrink-0 flex-col">
              <div className="grid grid-cols-2 gap-2 p-3 text-xs">
                <label>
                  Store scope
                  <select
                    aria-label="Store scope"
                    value={scope}
                    onChange={(e) => setScope(e.target.value)}
                    className={`mt-1 w-full ${control}`}
                  >
                    <option value="debug">Debug · reconstruct all local stores</option>
                    {PRINCIPALS.map((p) => (
                      <option key={p} value={p}>
                        {NAMES[p]}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Message / event
                  <select
                    aria-label="Store snapshot"
                    value={selection.event ?? "latest"}
                    onChange={(e) =>
                      setSelection(
                        e.target.value === "latest"
                          ? {}
                          : { event: Number(e.target.value), side: "after" },
                      )
                    }
                    className={`mt-1 w-full ${control}`}
                  >
                    <option value="latest">Latest</option>
                    {state.liveEvents.map((event) => (
                      <option key={event.seq} value={event.seq}>
                        {event.seq} · {event.message} · {event.kind}
                      </option>
                    ))}
                  </select>
                </label>
                {selection.event && (
                  <div className="col-span-2 flex gap-1">
                    {(["before", "after", "check"] as const).map((side) => (
                      <Button
                        key={side}
                        size="sm"
                        variant={selection.side === side ? "secondary" : "ghost"}
                        onClick={() => setSelection((s) => ({ ...s, side }))}
                      >
                        {side === "check" ? "Gate inputs" : side === "before" ? "Before" : "After"}
                      </Button>
                    ))}
                  </div>
                )}
              </div>
              <div
                className="min-h-0 flex-1 overflow-auto px-3 pb-3 text-xs"
                data-testid="inspector-facts"
              >
                {(["config", "input", "derived"] as const).map((group) => {
                  const rows =
                    group === "derived"
                      ? state.derived
                          .filter((r) => scope === "debug" || r.owners.includes(scope))
                          .map((r) => ({
                            fact: r.fact,
                            label: `${r.owners.join(", ")} · ${r.rule}`,
                          }))
                      : state.records
                          .filter(
                            (r) =>
                              (group === "config"
                                ? r.source === "config"
                                : r.source !== "config") &&
                              (scope === "debug" || r.owner === scope),
                          )
                          .map((r) => ({
                            fact: r.fact,
                            label: `${r.source}${r.replicated ? " (replicated)" : ""} · ${r.lifetime === "local" ? `local at ${r.owner}` : r.lifetime}${r.event ? ` · event ${r.event}` : ""}`,
                          }));
                  return (
                    <details key={group} open={group === "derived"} className="mb-3">
                      <summary className="cursor-pointer font-medium">
                        {group === "config"
                          ? "Configuration"
                          : group === "input"
                            ? "Runtime / trusted input"
                            : "Derived · Datalog closure"}{" "}
                        · {rows.length}
                      </summary>
                      <div className="mt-2 space-y-1.5">
                        {rows.map((row, i) => (
                          <div key={i} className="rounded bg-muted/60 p-2">
                            <code className="break-all">{format(row.fact)}</code>
                            <p className="mt-1 text-muted-foreground">{row.label}</p>
                          </div>
                        ))}
                      </div>
                    </details>
                  );
                })}
              </div>
            </div>
            <AnalysisTerminal scope={scope} state={state} selection={selection} mutate={mutate} />
          </aside>
        )}
      </div>
      <Dialog open={protocolOpen} onOpenChange={setProtocolOpen}>
        <DialogContent className="max-h-[85vh] overflow-auto">
          <DialogTitle>Local stores and transfers</DialogTitle>
          <pre className="overflow-auto text-xs">{JSON.stringify(state?.protocol, null, 2)}</pre>
        </DialogContent>
      </Dialog>
      <Dialog open={rules} onOpenChange={setRules}>
        <DialogContent className="max-h-[85vh] overflow-auto sm:max-w-3xl">
          <DialogTitle>Executable policy rules</DialogTitle>
          <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed">
            {state?.rules}
          </pre>
        </DialogContent>
      </Dialog>
      <Dialog open={configOpen} onOpenChange={setConfigOpen}>
        <DialogContent>
          <DialogTitle>Application configuration</DialogTitle>
          <textarea
            aria-label="Application configuration"
            value={config}
            onChange={(e) => setConfig(e.target.value)}
            rows={9}
            className="w-full rounded border border-border bg-background p-2 font-mono text-xs"
          />
          <Button
            disabled={busy}
            onClick={() =>
              void mutate({ operation: "config", config }).then(() => setConfigOpen(false))
            }
          >
            Apply configuration
          </Button>
        </DialogContent>
      </Dialog>
    </main>
  );
}
