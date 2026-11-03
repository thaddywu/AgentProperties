import type { closureConformance, comparePrevention } from "@rakazo/nova/prevention";
import type { NovaView, Request, Selection } from "@rakazo/nova/service";
import type { PolicyReview } from "@rakazo/nova/translation-review";
import {
  Button,
  Dialog,
  DialogContent,
  DialogTitle,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@rakazo/ui-web";
import { useEffect, useState } from "react";
import { request } from "./client";
import { PolicyData, ProtocolDetails } from "./PolicyData";
import { TranslationComparison } from "./TranslationComparison";

const codeStyle = "whitespace-pre-wrap break-words font-mono text-xs leading-relaxed";
function Details({ title, value }: { title: string; value: unknown }) {
  return (
    <details className="text-xs">
      <summary className="cursor-pointer font-medium">{title}</summary>
      <div className="mt-2">
        <PolicyData value={value} />
      </div>
    </details>
  );
}
function Layer({ layer, state }: { layer: NovaView["policyLayers"][number]; state: NovaView }) {
  const values = state.configuration.filter((fact) =>
    layer.predicates.some((predicate) => predicate.name === fact.predicate),
  );
  return (
    <>
      <section aria-label={`${layer.title} EDB`} className="space-y-2">
        <h3 className="text-xs font-medium">EDB · input schema</h3>
        <div className="space-y-1 text-xs">
          {layer.predicates
            .filter((p) => p.kind === "input")
            .map((p) => (
              <div key={p.name} className="flex flex-wrap justify-between gap-x-3 gap-y-1">
                <code className="break-all">
                  {p.name}({p.args.join(", ")})
                </code>
                <span className="text-muted-foreground">{p.source}</span>
              </div>
            ))}
        </div>
        {values.length > 0 && (
          <Details
            title="App-supplied values"
            value={values.map((f) => `${f.predicate}(${f.args.join(", ")}).`).join("\n")}
          />
        )}
      </section>
      <Details
        title="IDB · derived schema"
        value={layer.predicates
          .filter((p) => p.kind === "derived")
          .map((p) => `${p.name}(${p.args.join(", ")})`)
          .join("\n")}
      />
      <section aria-label={`${layer.title} rules`} className="space-y-3">
        <h3 className="text-xs font-medium">Inference rules · {layer.rules.length}</h3>
        {layer.rules.map((rule) => (
          <div key={rule.id} className="rounded border border-border p-3">
            <p className="mb-2 text-xs text-muted-foreground">{rule.id}</p>
            <pre className={codeStyle}>{rule.text}</pre>
          </div>
        ))}
      </section>
    </>
  );
}
export function PolicyLayers({
  state,
  open,
  onOpenChange,
  mutate,
  busy,
  selection,
  tab,
  setTab,
  review,
  setReview,
  replay,
  parentError,
}: {
  state: NovaView | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mutate: (request: Request) => Promise<void>;
  busy: boolean;
  selection: Selection;
  tab: string;
  setTab: (value: string) => void;
  review?: PolicyReview;
  setReview: (value: PolicyReview | undefined) => void;
  replay: () => Promise<void>;
  parentError?: string;
}) {
  const [trials, setTrials] = useState<ReturnType<typeof comparePrevention>>();
  const [conformance, setConformance] = useState<ReturnType<typeof closureConformance>>();
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    setConformance(undefined);
    setTrials(undefined);
  }, [state?.version, selection.event, selection.side, review?.artifact.id]);
  const artifact = review?.artifact ?? state?.policy;
  const displayedTrials = trials ?? (review?.historical ? undefined : review?.cases);
  async function perform(action: () => Promise<void>) {
    setWorking(true);
    setError("");
    try {
      await action();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Request failed");
    } finally {
      setWorking(false);
    }
  }
  const disabled = working || busy || !state;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-auto sm:max-w-6xl">
        <DialogTitle>Rules and inputs</DialogTitle>
        {state && (
          <p className="text-xs text-muted-foreground">
            Active: {state.policyIdentity.mode === "golden" ? "Reference" : "Translated"} ·{" "}
            {state.policyIdentity.id.slice(0, 12)}
          </p>
        )}
        {(error || parentError) && (
          <p role="alert" className="text-xs text-destructive">
            {error || parentError}
          </p>
        )}
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList
            aria-label="Policy walkthrough"
            className="w-full flex-wrap justify-start group-data-horizontal/tabs:h-auto"
          >
            {[
              ["runtime", "Runtime"],
              ["input", "Nova input"],
              ["translated", "Translated"],
              ["golden", "Reference"],
              ["prevention", "Prevention"],
            ].map(([id, title]) => (
              <TabsTrigger key={id} value={id!} className="h-7 flex-none">
                {title}
              </TabsTrigger>
            ))}
          </TabsList>
          <TabsContent value="runtime" className="min-w-0 space-y-4">
            <p className="text-xs text-muted-foreground">
              Fixed IFC and capability rules. Configuration values come from the app.
            </p>
            {state && (
              <>
                <ProtocolDetails title="Built-in protocol" protocol={state.foundationProtocol} />
                <Layer state={state} layer={state.policyLayers[0]!} />
              </>
            )}
          </TabsContent>
          <TabsContent value="input" className="min-w-0 space-y-4">
            <p className="text-xs text-muted-foreground">
              Application specification, policies, agents and tools. Episodes are optional.
            </p>
            {state?.documents.map((doc) => (
              <Details key={doc.path} title={doc.path} value={doc.content} />
            ))}
          </TabsContent>
          <TabsContent value="translated" className="min-w-0 space-y-4">
            {(busy || working) && (
              <p role="status" className="text-xs text-muted-foreground">
                Loading translation…
              </p>
            )}
            <div className="flex flex-wrap items-center gap-3">
              <Button size="sm" disabled={disabled} onClick={() => void replay()}>
                View saved translation
              </Button>
              <span className="text-xs text-muted-foreground">
                Saved model output and its recorded comparison. No model call.
              </span>
            </div>
            <label className="block text-xs font-medium">
              Import translation artifact
              <input
                aria-label="Import translation artifact"
                className="mt-2 block w-full text-xs"
                type="file"
                accept=".json,application/json"
                disabled={disabled}
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  event.target.value = "";
                  if (!file || !state) return;
                  setReview(undefined);
                  void perform(async () => {
                    if (file.size > 200_000) throw new Error("Artifact exceeds 200 KB.");
                    const result = await request<PolicyReview>({
                      operation: "review-policy",
                      revision: state.version,
                      artifact: JSON.parse(await file.text()),
                    });
                    setReview(result);
                    setTrials(result.cases);
                  });
                }}
              />
            </label>
            {!artifact && (
              <p className="text-xs text-muted-foreground">
                Import nova-policy.json from the one-shot extension command.
              </p>
            )}
            {artifact && (
              <>
                <p className="text-xs text-muted-foreground">
                  {artifact.model} · {artifact.id.slice(0, 12)} · Fixed protocol inherited; protocol
                  synthesis is not implemented.
                </p>
                {review && (
                  <p className="text-xs">
                    {review.historical
                      ? "Historical protocol: saved results only. Cannot run or activate in the current runtime."
                      : review.eligible
                        ? "Checks passed; semantic equivalence is unproven."
                        : "Checks failed. See Prevention for counterexamples."}
                  </p>
                )}
                {review?.eligible && (
                  <Button
                    size="sm"
                    disabled={disabled}
                    onClick={() => void mutate({ operation: "start-policy", artifact })}
                  >
                    Start translated session
                  </Button>
                )}
                <Details title="Exact translation input" value={artifact.documents} />
                <ProtocolDetails title="Inherited protocol" protocol={artifact.protocol} />
                {review && (
                  <>
                    <p className="text-xs text-muted-foreground">
                      {review.cases.filter((test) => test.matches).length} of {review.cases.length}{" "}
                      scenarios matched. This is not a proof of equivalence.
                    </p>
                    {review.historical && (
                      <Details title="Historical checks" value={review.cases} />
                    )}
                    <TranslationComparison
                      rows={review.correspondence}
                      historical={review.historical}
                    />
                  </>
                )}
                {!review && (
                  <Button
                    size="sm"
                    disabled={disabled}
                    onClick={() =>
                      void perform(async () => {
                        if (state)
                          setReview(
                            await request<PolicyReview>({
                              operation: "review-policy",
                              revision: state.version,
                              artifact,
                            }),
                          );
                      })
                    }
                  >
                    Compare active translation
                  </Button>
                )}
              </>
            )}
          </TabsContent>
          <TabsContent value="golden" className="min-w-0 space-y-4">
            <p className="text-xs text-muted-foreground">
              Handwritten Nova rules and protocol. Combined with the fixed runtime foundation.
            </p>
            <Button
              size="sm"
              disabled={disabled}
              onClick={() => void mutate({ operation: "start-policy" })}
            >
              Start reference session
            </Button>
            {state && (
              <>
                <ProtocolDetails title="Nova protocol" protocol={state.applicationProtocol} />
                <ProtocolDetails title="Complete protocol" protocol={state.protocol} />
                <Layer state={state} layer={state.policyLayers[1]!} />
              </>
            )}
          </TabsContent>
          <TabsContent value="prevention" className="min-w-0 space-y-4">
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                disabled={disabled}
                onClick={() =>
                  void perform(async () => {
                    if (!state) return;
                    if (review?.historical) {
                      setTrials(
                        await request({ operation: "prevention", revision: state.version }),
                      );
                    } else if (artifact) {
                      const result = await request<PolicyReview>({
                        operation: "review-policy",
                        revision: state.version,
                        artifact,
                      });
                      setReview(result);
                      setTrials(result.cases);
                    } else
                      setTrials(
                        await request({ operation: "prevention", revision: state.version }),
                      );
                  })
                }
              >
                Run prevention comparison
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={disabled}
                onClick={() =>
                  void perform(async () => {
                    if (state)
                      setConformance(
                        await request({
                          operation: "conformance",
                          revision: state.version,
                          ...selection,
                        }),
                      );
                  })
                }
              >
                Check closure union
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              {review?.historical
                ? "Checks use the current runtime. The saved translation belongs to an older protocol."
                : "Prevention uses fresh sessions and baseline configuration. Closure comparison uses the selected snapshot."}
            </p>
            {conformance && (
              <div className="space-y-2 text-xs">
                <p>
                  {conformance.equivalent
                    ? "Local closure union, global completion and pending gate decisions match full-copy."
                    : "Full-copy mismatch found."}
                </p>
                <p>
                  Stored EDB copies: {conformance.storedInputCopies} · Full-copy:{" "}
                  {conformance.fullCopyInputCopies}
                </p>
                <Details title="Closure evidence" value={conformance} />
              </div>
            )}
            {displayedTrials?.map((trial) => (
              <section
                key={trial.name}
                className="space-y-2 rounded border border-border p-3 text-xs"
              >
                <h3 className="font-medium">{trial.name}</h3>
                <p>
                  Reference: {trial.golden.passed ? "passed" : "failed"}
                  {trial.translated
                    ? ` · Translated: ${trial.matches && trial.translated.passed ? "matched" : "mismatch"}`
                    : " · No translation loaded"}
                </p>
                <Details
                  title="Delivery and payload evidence"
                  value={{
                    golden: trial.golden.observations,
                    translated: trial.translated?.observations,
                    errors: [trial.golden.error, trial.translated?.error].filter(Boolean),
                  }}
                />
                {trial.matches === false && (
                  <Details title="Closure and visibility counterexample" value={trial.difference} />
                )}
              </section>
            ))}
            {state && <Details title="Active executable rules" value={state.rules} />}
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
