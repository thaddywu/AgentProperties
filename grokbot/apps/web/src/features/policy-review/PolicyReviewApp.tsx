import type {
  ReviewBehavior,
  ReviewFeedback,
  ReviewWorkspace,
  TranslationReview,
} from "@rakazo/policy-translation/review-contract";
import { Button, Dialog, DialogContent, DialogTitle } from "@rakazo/ui-web";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronDown,
  Download,
  Pencil,
  RotateCcw,
  ScanLine,
} from "lucide-react";
import { useEffect, useState } from "react";
import { AppearanceToggle } from "../../components/AppearanceToggle";
import { LoadingState } from "../../components/ai/primitives";
import {
  draftKey,
  exportReview,
  readDraft,
  readFeedback,
  reviewRequest,
  storageKey,
} from "./client";

const clean = (text: string) => text.replace(/\*\*/g, "");
const title = (text: string) =>
  /^\*\*([^*]+)\*\*/.exec(text)?.[1]?.replace(/:$/, "") ?? text.slice(0, 60);
const control =
  "rounded-lg border border-border bg-background px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-ring";
const ratings = [
  { value: "matches", label: "Matches" },
  { value: "different", label: "Different" },
  { value: "unsure", label: "Not sure" },
] as const;
const differences = [
  { value: "missing", label: "Something missing" },
  { value: "stricter", label: "Too restrictive" },
  { value: "weaker", label: "Too permissive" },
  { value: "meaning", label: "Different meaning" },
] as const;

function Original({
  review,
  policyId,
  behavior,
  onSelect,
}: {
  review: TranslationReview;
  policyId: string;
  behavior: ReviewBehavior;
  onSelect: (id: string) => void;
}) {
  const policy = review.policies.find((p) => p.id === policyId)!;
  const requirements = review.requirements.filter((r) => r.policyId === policyId);
  // Split at all boundaries so overlapping requirements preserve the exact original text.
  const boundaries = [
    ...new Set([0, policy.text.length, ...requirements.flatMap((r) => [r.start, r.end])]),
  ].sort((a, b) => a - b);
  return (
    <div className="text-base leading-8">
      {boundaries.slice(0, -1).map((start, index) => {
        const end = boundaries[index + 1]!;
        const related = requirements.filter((r) => r.start < end && r.end > start);
        const selected = related.some((r) => behavior.requirementIds.includes(r.id));
        const gap = related.some((r) => ["unsupported", "ambiguous"].includes(r.implementation));
        const target = review.behaviors.find((b) =>
          related.some((r) => b.requirementIds.includes(r.id)),
        );
        const text = clean(policy.text.slice(start, end));
        return target ? (
          <button
            key={start}
            type="button"
            aria-pressed={selected}
            onClick={() => onSelect(target.id)}
            className={`inline rounded px-0.5 text-left transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring ${selected ? "bg-primary/10 text-foreground" : "text-muted-foreground"} ${gap ? "underline decoration-warning decoration-dotted underline-offset-4" : ""}`}
          >
            {text}
          </button>
        ) : (
          <span key={start}>{text}</span>
        );
      })}
    </div>
  );
}

export function PolicyReviewApp() {
  const [workspace, setWorkspace] = useState<ReviewWorkspace>();
  const [reference, setReference] = useState<ReviewWorkspace>();
  const [savedDraft, setSavedDraft] = useState<TranslationReview>();
  const [policyId, setPolicyId] = useState("P1");
  const [active, setActive] = useState("");
  const [feedback, setFeedback] = useState<Record<string, ReviewFeedback>>({});
  const [error, setError] = useState("");
  const [storageError, setStorageError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [editError, setEditError] = useState("");
  const [onlyUnreviewed, setOnlyUnreviewed] = useState(false);
  const [onlyGaps, setOnlyGaps] = useState(false);

  const activate = (next: ReviewWorkspace) => {
    setWorkspace(next);
    setPolicyId(next.review.policies[0]!.id);
    setActive(next.review.behaviors[0]?.id ?? "");
    setOnlyUnreviewed(false);
    setOnlyGaps(false);
    setDraft(next.review.sourceText);
    try {
      setFeedback(readFeedback(localStorage.getItem(storageKey(next.review)), next.review));
      if (next.review.origin === "model") {
        localStorage.setItem(draftKey, JSON.stringify(next.review));
        setSavedDraft(next.review);
      }
      setStorageError(false);
    } catch {
      setFeedback({});
      setStorageError(true);
    }
  };
  useEffect(() => {
    let alive = true;
    reviewRequest({ operation: "load" })
      .then((next) => {
        if (!alive) return;
        setReference(next);
        let cached: TranslationReview | undefined;
        try {
          cached = readDraft(localStorage.getItem(draftKey), next.review);
        } catch {
          /* Storage may be disabled. */
        }
        activate(cached ? { ...next, review: cached } : next);
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, []);

  const review = workspace?.review;
  const linked = (behavior: ReviewBehavior, id: string) =>
    review!.requirements.some((r) => r.policyId === id && behavior.requirementIds.includes(r.id));
  const items =
    review?.behaviors.filter(
      (b) =>
        linked(b, policyId) &&
        (!onlyGaps || b.kind === "gap") &&
        (!onlyUnreviewed || !feedback[b.id]?.rating || b.id === active),
    ) ?? [];
  const item = items.find((b) => b.id === active) ?? items[0];
  const itemIndex = item ? items.indexOf(item) : -1;
  const response = item ? (feedback[item.id] ?? { note: "" }) : { note: "" };
  const reviewed = review?.behaviors.filter((b) => feedback[b.id]?.rating).length ?? 0;

  const update = (change: Partial<ReviewFeedback>) => {
    if (!review || !item) return;
    setActive(item.id);
    const next = { ...feedback, [item.id]: { ...response, ...change } };
    setFeedback(next);
    try {
      localStorage.setItem(storageKey(review), JSON.stringify(next));
      setStorageError(false);
    } catch {
      setStorageError(true);
    }
  };
  const download = () => {
    if (!review) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(exportReview(review, feedback), null, 2)], {
        type: "application/json",
      }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `policy-review-${review.id.slice(0, 12)}.json`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const translate = async () => {
    setBusy(true);
    setEditError("");
    try {
      activate(await reviewRequest({ operation: "translate", policyText: draft }));
      setEditing(false);
    } catch (e) {
      setEditError(e instanceof Error ? e.message : "Translation failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="min-h-full bg-background text-foreground">
      <header className="flex min-h-16 flex-wrap items-center gap-3 border-b border-border px-5 py-3 sm:px-8">
        <ScanLine className="size-5" aria-hidden />
        <a href="/policy-review.html" className="text-sm font-semibold tracking-tight">
          PolicyScope
        </a>
        <span className="text-sm text-muted-foreground">{review?.application ?? "Review"}</span>
        <div className="ml-auto flex items-center gap-2">
          <AppearanceToggle />
          {review?.origin === "model" && (
            <Button variant="ghost" size="sm" onClick={() => reference && activate(reference)}>
              <RotateCcw className="size-3.5" />
              Reference
            </Button>
          )}
          {review?.origin === "reference" && savedDraft && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => activate({ ...workspace!, review: savedDraft })}
            >
              Resume draft
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            disabled={!review || busy}
            onClick={() => {
              setDraft(review!.sourceText);
              setEditError("");
              setEditing(true);
            }}
          >
            <Pencil className="size-3.5" />
            Edit policy
          </Button>
          <Button variant="outline" size="sm" disabled={!review} onClick={download}>
            <Download className="size-3.5" />
            Export review
          </Button>
        </div>
      </header>
      {error && (
        <p role="alert" className="mx-auto max-w-5xl p-8 text-destructive">
          {error}
        </p>
      )}
      {!review && !error && (
        <div className="p-8">
          <LoadingState label="Loading policies" />
        </div>
      )}
      {review && (
        <div className="mx-auto max-w-7xl px-5 py-8 sm:px-8 sm:py-12">
          <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
            <div>
              <h1 className="text-2xl font-medium tracking-tight">Does this match your policy?</h1>
              <p className="mt-2 text-sm text-muted-foreground">
                {review.origin === "reference"
                  ? "Reference reading · hand-authored"
                  : "Model translation · draft"}
              </p>
            </div>
            <span className="text-sm tabular-nums text-muted-foreground" aria-live="polite">
              {reviewed} / {review.behaviors.length} reviewed
            </span>
          </div>
          <nav aria-label="Policies" className="mb-8 flex flex-wrap gap-2">
            {review.policies.map((policy) => (
              <button
                key={policy.id}
                type="button"
                aria-label={`${policy.id} ${title(policy.text)}`}
                aria-current={policyId === policy.id ? "page" : undefined}
                onClick={() => {
                  setPolicyId(policy.id);
                  setActive("");
                }}
                className={`rounded-lg border px-3 py-2 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-ring ${policyId === policy.id ? "border-primary bg-primary text-primary-foreground" : "border-border hover:bg-muted"}`}
              >
                <span className="mr-2 opacity-60">{policy.id}</span>
                {title(policy.text)}
              </button>
            ))}
          </nav>
          <div className="grid items-start gap-8 lg:grid-cols-2 lg:gap-14">
            <section aria-label="Original policy" className="min-w-0">
              <div className="mb-5 flex items-center gap-2 text-xs text-muted-foreground">
                <span>Original</span>
                <span className="ml-auto">{policyId}</span>
              </div>
              {item ? (
                <Original
                  review={review}
                  policyId={policyId}
                  behavior={item}
                  onSelect={(id) => {
                    setOnlyUnreviewed(false);
                    setOnlyGaps(false);
                    setActive(id);
                  }}
                />
              ) : (
                <p className="text-base leading-8 text-muted-foreground">
                  {clean(review.policies.find((p) => p.id === policyId)!.text)}
                </p>
              )}
              {item && review.policies.some((p) => p.id !== policyId && linked(item, p.id)) && (
                <div className="mt-6 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <span>Also linked to</span>
                  {review.policies
                    .filter((p) => p.id !== policyId && linked(item, p.id))
                    .map((p) => (
                      <Button
                        key={p.id}
                        size="sm"
                        variant="outline"
                        onClick={() => setPolicyId(p.id)}
                      >
                        {p.id}
                      </Button>
                    ))}
                </div>
              )}
            </section>
            <section aria-label="Policy interpretation" className="min-w-0">
              <div className="mb-4 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                <span>Interpretation</span>
                <label className="ml-auto flex cursor-pointer items-center gap-1.5">
                  <input
                    type="checkbox"
                    checked={onlyGaps}
                    onChange={(e) => setOnlyGaps(e.target.checked)}
                  />
                  Unmapped
                </label>
                <label className="flex cursor-pointer items-center gap-1.5">
                  <input
                    type="checkbox"
                    checked={onlyUnreviewed}
                    onChange={(e) => {
                      setActive("");
                      setOnlyUnreviewed(e.target.checked);
                    }}
                  />
                  Unreviewed
                </label>
              </div>
              {!item ? (
                <div className="rounded-xl border border-dashed border-border p-8 text-sm text-muted-foreground">
                  No matching items.
                </div>
              ) : (
                <article
                  key={item.id}
                  className="rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-7"
                >
                  <div className="mb-5 flex items-center gap-2 text-xs text-muted-foreground">
                    <span>
                      {item.kind === "gap"
                        ? "Unmapped"
                        : item.kind === "integration"
                          ? "Application requirement · not verified here"
                          : "Rule behavior"}
                    </span>
                    {item.kind === "rule" &&
                      review.requirements.some(
                        (r) => item.requirementIds.includes(r.id) && r.relation !== "equivalent",
                      ) && <span className="text-warning">Partial mapping</span>}
                    {feedback[item.id]?.rating && (
                      <Check className="ml-auto size-3.5" aria-label="Reviewed" />
                    )}
                  </div>
                  <p
                    className="text-lg font-medium leading-7 tracking-tight"
                    data-testid="behavior-summary"
                  >
                    {item.summary}
                  </p>
                  <details className="group mt-5 text-sm">
                    <summary className="flex cursor-pointer list-none items-center gap-2 text-muted-foreground">
                      <ChevronDown className="size-3.5 transition-transform group-open:rotate-180" />
                      {item.kind === "gap" ? "What is missing" : "Conditions & evidence"}
                    </summary>
                    <ul className="mt-4 space-y-3 pl-5 list-disc text-sm leading-6">
                      {item.conditions.map((condition, i) => (
                        <li key={`${i}-${condition}`}>{condition}</li>
                      ))}
                    </ul>
                    {item.evidence.length > 0 && (
                      <details className="mt-5 border-t border-border pt-3">
                        <summary className="cursor-pointer text-muted-foreground">
                          Application inputs ({item.evidence.length})
                        </summary>
                        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-6">
                          {item.evidence.map((e) => (
                            <li key={e.name}>{e.meaning}</li>
                          ))}
                        </ul>
                      </details>
                    )}
                  </details>
                  {item.question && (
                    <div className="mt-6 rounded-lg bg-muted/60 p-4">
                      <p className="text-sm leading-6">{item.question}</p>
                      <fieldset className="mt-3 flex gap-2" aria-label="Your expected behavior">
                        {[
                          { value: "yes", label: "Yes" },
                          { value: "no", label: "No" },
                          { value: "unsure", label: "Not sure" },
                        ].map((choice) => (
                          <Button
                            key={choice.value}
                            size="sm"
                            variant={response.expectation === choice.value ? "default" : "outline"}
                            aria-pressed={response.expectation === choice.value}
                            onClick={() =>
                              update({ expectation: choice.value as ReviewFeedback["expectation"] })
                            }
                          >
                            {choice.label}
                          </Button>
                        ))}
                      </fieldset>
                    </div>
                  )}
                  <div className="mt-7 border-t border-border pt-5">
                    <fieldset
                      className="flex flex-wrap gap-2"
                      aria-label="Does this match your intent?"
                    >
                      {ratings.map((rating) => (
                        <Button
                          key={rating.value}
                          size="sm"
                          variant={response.rating === rating.value ? "default" : "outline"}
                          aria-pressed={response.rating === rating.value}
                          onClick={() =>
                            update({
                              rating: rating.value,
                              difference:
                                rating.value === "different" ? response.difference : undefined,
                            })
                          }
                        >
                          {rating.label}
                        </Button>
                      ))}
                    </fieldset>
                    {response.rating === "different" && (
                      <fieldset
                        className="mt-4 flex flex-wrap gap-2"
                        aria-label="Type of difference"
                      >
                        {differences.map((difference) => (
                          <button
                            key={difference.value}
                            type="button"
                            aria-pressed={response.difference === difference.value}
                            className={`${control} ${response.difference === difference.value ? "border-primary bg-muted" : "text-muted-foreground"}`}
                            onClick={() => update({ difference: difference.value })}
                          >
                            {difference.label}
                          </button>
                        ))}
                      </fieldset>
                    )}
                    {(response.rating || response.note) && (
                      <textarea
                        aria-label="Review note"
                        className={`${control} mt-4 min-h-24 w-full resize-y`}
                        maxLength={4000}
                        value={response.note}
                        onChange={(e) => update({ note: e.target.value })}
                        placeholder={
                          response.rating === "different"
                            ? "What should happen instead?"
                            : "Add a note…"
                        }
                      />
                    )}
                  </div>
                  <div className="mt-6 flex items-center justify-between text-xs text-muted-foreground">
                    <span>
                      {itemIndex + 1} / {items.length}
                    </span>
                    <div className="flex gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label="Previous interpretation"
                        disabled={itemIndex <= 0}
                        onClick={() => setActive(items[itemIndex - 1]!.id)}
                      >
                        <ArrowLeft className="size-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label="Next interpretation"
                        disabled={itemIndex >= items.length - 1}
                        onClick={() => setActive(items[itemIndex + 1]!.id)}
                      >
                        <ArrowRight className="size-4" />
                      </Button>
                    </div>
                  </div>
                </article>
              )}
              <p className="mt-4 text-xs text-muted-foreground" role="status">
                {storageError
                  ? "Browser storage is unavailable. Export to keep your feedback."
                  : "Feedback saved in this browser."}
              </p>
            </section>
          </div>
        </div>
      )}
      <Dialog
        open={editing}
        onOpenChange={(open) => {
          if (!busy) setEditing(open);
        }}
      >
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
          <DialogTitle>Edit policy</DialogTitle>
          <textarea
            aria-label="Policy text"
            spellCheck={false}
            className={`${control} min-h-80 w-full resize-y leading-7`}
            value={draft}
            maxLength={24000}
            disabled={busy}
            onChange={(e) => setDraft(e.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            Keep P1., P2., … as separate paragraphs. Translation uses the existing LabCluster
            inputs.
          </p>
          {editError && (
            <p role="alert" className="text-sm text-destructive">
              {editError}
            </p>
          )}
          <div className="flex flex-wrap items-center justify-end gap-3">
            {busy && (
              <div className="mr-auto" role="status">
                <LoadingState label="Translating and reading back" />
              </div>
            )}
            <Button variant="ghost" disabled={busy} onClick={() => setEditing(false)}>
              Cancel
            </Button>
            <Button disabled={busy || !draft.trim()} onClick={() => void translate()}>
              Translate
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </main>
  );
}
