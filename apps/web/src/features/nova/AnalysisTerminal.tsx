import type { ProofNode, SearchNode } from "@rakazo/core/policy/reasoning/analysis";
import { ACTION_PRESET, PREVENTABLE_PRESET } from "@rakazo/core/policy/reasoning/analysis";
import type { NovaView, Request, Selection } from "@rakazo/core/policy/reasoning/service";
import { Button } from "@rakazo/ui-web";
import { useState } from "react";
import { request } from "./client";

const tabs = [
  { id: "query", label: "Terminal" },
  { id: "why", label: "Why" },
  { id: "what-if", label: "What-if" },
  { id: "minimal", label: "Prevention" },
  { id: "speculative", label: "Speculative" },
] as const;
type Tab = (typeof tabs)[number]["id"];
function Field({
  label,
  value,
  onChange,
  rows = 3,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  rows?: number;
}) {
  return (
    <label className="block min-w-0 space-y-1 text-xs">
      <span className="font-medium">{label}</span>
      <textarea
        aria-label={label}
        value={value}
        rows={rows}
        onChange={(e) => onChange(e.target.value)}
        spellCheck={false}
        className="w-full resize-y rounded border border-border bg-background p-2 font-mono text-xs leading-relaxed"
      />
    </label>
  );
}
export function ProofTree({ node }: { node: ProofNode }) {
  return node.children.length ? (
    <details open className="my-1">
      <summary className="cursor-pointer break-all font-mono">
        <span>{node.fact}</span>
        <span className="ml-2 font-sans text-muted-foreground">{node.rule}</span>
      </summary>
      <div className="ml-2 border-l border-border pl-3">
        {node.children.map((child, i) => (
          <ProofTree key={i} node={child} />
        ))}
      </div>
    </details>
  ) : (
    <div className="my-1 break-all font-mono">
      {node.fact}
      <span className="ml-2 font-sans text-muted-foreground">{node.kind}</span>
    </div>
  );
}
function SearchTree({ node }: { node: SearchNode }) {
  return (
    <div className="space-y-2">
      {node.finished && <strong className="text-success">Finished</strong>}
      {!node.finished && !node.edges.length && <span>Dead end · no progress actions</span>}
      {node.edges.map((edge) => (
        <details key={edge.action.id} className="rounded border border-border p-2">
          <summary className="cursor-pointer">
            <code>{edge.action.id}</code>
            <span
              className={`ml-2 ${edge.classification === "denied" ? "text-destructive" : edge.classification === "completion-preserving" ? "text-success" : "text-muted-foreground"}`}
            >
              {edge.classification}
            </span>
          </summary>
          <div className="mt-2 border-l border-border pl-2">
            {edge.trace && (
              <p className="mb-2 font-mono">{edge.trace.map((a) => a.id).join(" → ")}</p>
            )}
            {edge.successor && <SearchTree node={edge.successor} />}
            {edge.proof && <ProofTree node={edge.proof} />}
          </div>
        </details>
      ))}
    </div>
  );
}
type Result = {
  revision: number;
  context: string;
  data?: unknown;
  error?: string;
  basis?: "earlier" | "selected";
  selection?: Selection;
};
export function AnalysisTerminal({
  state,
  selection,
  mutate,
}: {
  state: NovaView;
  selection: Selection;
  mutate: (req: Request) => Promise<void>;
}) {
  const [tab, setTab] = useState<Tab>("query");
  const [program, setProgram] = useState("?- Knows(A, nova, Part).");
  const [whyQuery, setWhyQuery] = useState("DenyReceive(auditor_a, mH)");
  const [whatQuery, setWhatQuery] = useState("DenyReceive(auditor_a, mH)");
  const [minQuery, setMinQuery] = useState("DenyReceive(auditor_a, mH)");
  const [remove, setRemove] = useState("Receiver(auditor_a, mF).\nReceived(auditor_a, mF).");
  const [add, setAdd] = useState("");
  const [events, setEvents] = useState(PREVENTABLE_PRESET);
  const [goal, setGoal] = useState("Finished(nova)");
  const [actions, setActions] = useState(ACTION_PRESET);
  const [basis, setBasis] = useState<"earlier" | "selected">("earlier");
  const [results, setResults] = useState<Partial<Record<Tab, Result>>>({});
  const [busy, setBusy] = useState(false);
  const result = results[tab];
  const run = async () => {
    setBusy(true);
    const context =
      tab === "speculative" && basis === "earlier"
        ? "Earlier runtime · Procurement received by A"
        : selection.event
          ? `Event ${selection.event} · ${selection.side}`
          : "Current runtime";
    try {
      const data = await request({
        operation: tab,
        revision: state.version,
        ...selection,
        query:
          tab === "query"
            ? program
            : tab === "why"
              ? whyQuery
              : tab === "what-if"
                ? whatQuery
                : minQuery,
        remove,
        add,
        events,
        goal,
        actions,
        basis,
      });
      setResults((prev) => ({
        ...prev,
        [tab]: { revision: state.version, context, data, basis, selection: { ...selection } },
      }));
    } catch (e) {
      setResults((prev) => ({
        ...prev,
        [tab]: {
          revision: state.version,
          context,
          error: e instanceof Error ? e.message : "Analysis failed",
        },
      }));
    } finally {
      setBusy(false);
    }
  };
  const help: Record<Tab, string> = {
    query: "Read-only Datalog over the selected global logical state.",
    why: "Trace a fact back to the rules and input events that derived it.",
    "what-if": "Evaluate (inputs − REMOVE) ∪ ADD on a copy.",
    minimal: "Find all smallest subsets of preventable events that remove the queried fact.",
    speculative: "Find a safe completion trace and classify every immediate progress action.",
  };
  return (
    <section
      aria-label="Datalog analysis terminal"
      className="flex min-h-0 flex-1 flex-col border-t border-border"
    >
      <div
        role="tablist"
        aria-label="Analysis tabs"
        className="flex shrink-0 overflow-x-auto border-b border-border p-1"
      >
        {tabs.map((t) => (
          <button
            type="button"
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`whitespace-nowrap rounded px-3 py-2 text-xs ${tab === t.id ? "bg-muted font-medium" : "text-muted-foreground"}`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div
        className="min-h-0 flex-1 space-y-3 overflow-auto p-3"
        role="tabpanel"
        aria-label={tabs.find((t) => t.id === tab)?.label}
        onKeyDown={(e) => {
          if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && !busy) {
            e.preventDefault();
            void run();
          }
        }}
      >
        <p className="text-xs text-muted-foreground">{help[tab]}</p>
        {tab === "query" && (
          <>
            <Field label="Datalog program" value={program} onChange={setProgram} rows={4} />
            <details className="text-xs text-muted-foreground">
              <summary className="cursor-pointer">Syntax</summary>
              <p className="mt-1">
                Facts and rules end with a period. Query with ?-. Supports variables, joins,
                recursion, not, !=, and _. Temporary input facts and custom rules are allowed;
                policy-derived predicates are read-only.
              </p>
            </details>
          </>
        )}
        {tab === "why" && (
          <Field label="PROOF query" value={whyQuery} onChange={setWhyQuery} rows={2} />
        )}
        {tab === "what-if" && (
          <>
            <Field label="REMOVE" value={remove} onChange={setRemove} />
            <Field label="ADD" value={add} onChange={setAdd} rows={2} />
            <Field label="QUERY" value={whatQuery} onChange={setWhatQuery} rows={2} />
          </>
        )}
        {tab === "minimal" && (
          <>
            <Field label="QUERY" value={minQuery} onChange={setMinQuery} rows={2} />
            <Field label="PREVENTABLE EVENTS" value={events} onChange={setEvents} rows={7} />
          </>
        )}
        {tab === "speculative" && (
          <>
            <label className="block text-xs">
              Starting state
              <select
                aria-label="Speculative starting state"
                value={basis}
                onChange={(e) => setBasis(e.target.value as typeof basis)}
                className="mt-1 w-full rounded border border-border bg-background p-2"
              >
                <option value="earlier">Earlier runtime · A has Procurement</option>
                <option value="selected">Selected runtime snapshot</option>
              </select>
            </label>
            <Field label="GOAL" value={goal} onChange={setGoal} rows={2} />
            <Field label="PROGRESS ACTIONS" value={actions} onChange={setActions} rows={6} />
          </>
        )}
        <Button size="sm" disabled={busy} onClick={() => void run()}>
          {busy
            ? "Running…"
            : tab === "why"
              ? "PROOF"
              : tab === "query"
                ? "Run query"
                : tab === "what-if"
                  ? "Run what-if"
                  : tab === "minimal"
                    ? "Find minimum"
                    : "Find completion"}
        </Button>
        {result && (
          <div
            className="space-y-2 border-t border-border pt-3 text-xs"
            aria-live="polite"
            data-testid="analysis-result"
          >
            <p className="text-muted-foreground">
              {result.context} · revision {result.revision}
              {result.revision !== state.version ? " · previous result" : ""}
            </p>
            {result.error ? (
              <p role="alert" className="text-destructive">
                {result.error}
              </p>
            ) : (
              <AnalysisResult
                tab={tab}
                data={result.data}
                replayDisabled={busy || result.revision !== state.version}
                onReplay={async (trace) => {
                  setBusy(true);
                  try {
                    await mutate({
                      operation: "replay-trace",
                      basis: result.basis,
                      trace,
                      ...result.selection,
                    });
                  } finally {
                    setBusy(false);
                  }
                }}
              />
            )}
          </div>
        )}
      </div>
    </section>
  );
}
function AnalysisResult({
  tab,
  data,
  onReplay,
  replayDisabled,
}: {
  tab: Tab;
  data: unknown;
  onReplay: (trace: string[]) => Promise<void>;
  replayDisabled: boolean;
}) {
  if (tab === "why")
    return data ? (
      <ProofTree node={data as ProofNode} />
    ) : (
      <p>Fact is not derived in this snapshot.</p>
    );
  if (tab === "query") {
    const result = data as { columns: string[]; rows: string[][] };
    return result.columns.length ? (
      <>
        <p>{result.rows.length} result(s)</p>
        <div className="overflow-x-auto">
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
              {result.rows.map((row, i) => (
                <tr key={i}>
                  {row.map((v, j) => (
                    <td key={j} className="border-b border-border p-1 font-mono">
                      {v}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </>
    ) : (
      <strong>RESULT: {result.rows.length ? "true" : "false"}</strong>
    );
  }
  if (tab === "what-if") {
    const result = data as {
      result: boolean;
      added: { predicate: string; args: string[] }[];
      removed: { predicate: string; args: string[] }[];
    };
    return (
      <>
        <strong>RESULT: {String(result.result)}</strong>
        {(["removed", "added"] as const).map((kind) => (
          <div key={kind}>
            <h4 className="my-2">
              Derived facts {kind} · {result[kind].length}
            </h4>
            <pre className="whitespace-pre-wrap break-all text-muted-foreground">
              {result[kind].map((f) => `${f.predicate}(${f.args.join(", ")})`).join("\n") || "None"}
            </pre>
          </div>
        ))}
      </>
    );
  }
  if (tab === "minimal") {
    const result = data as { size: number | null; solutions: string[][]; evaluated: number };
    return (
      <>
        <strong>
          {result.size === null
            ? "No solution in the configured event set"
            : `Minimum: ${result.size} event(s)`}
        </strong>
        {result.solutions.map((s, i) => (
          <pre key={i}>{`{ ${s.join(", ")} }`}</pre>
        ))}
        <p className="text-muted-foreground">{result.evaluated} subsets evaluated</p>
      </>
    );
  }
  const result = data as SearchNode & { evaluated: number };
  return (
    <>
      <strong>
        {result.trace ? "Completion exists" : "No completion in this action universe"}
      </strong>
      {result.trace && (
        <>
          <pre className="whitespace-pre-wrap">
            {result.trace.map((a) => a.id).join("\n") || "Goal already holds"}
          </pre>
          <Button
            size="sm"
            variant="outline"
            disabled={replayDisabled}
            onClick={() => void onReplay(result.trace!.map((a) => a.id))}
          >
            Replay completion in runtime
          </Button>
        </>
      )}
      <p className="text-muted-foreground">{result.evaluated} states evaluated</p>
      <SearchTree node={result} />
    </>
  );
}
