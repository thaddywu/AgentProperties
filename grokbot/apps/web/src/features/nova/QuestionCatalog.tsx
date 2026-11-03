import type { QuestionTemplate } from "@rakazo/nova/questions";
import { QUESTION_CATEGORIES, QUESTION_SUGGESTIONS, QUESTIONS } from "@rakazo/nova/questions";
import type { Selection } from "@rakazo/nova/service";
import { Button, Dialog, DialogContent, DialogTitle } from "@rakazo/ui-web";
import { useEffect, useRef, useState } from "react";
import { interpretQuestion } from "./client";

export function QuestionCatalog({
  open,
  revision,
  selection,
  onOpenChange,
  onSelect,
}: {
  open: boolean;
  revision: number;
  selection: Selection;
  onOpenChange: (open: boolean) => void;
  onSelect: (question: QuestionTemplate) => void;
}) {
  const [category, setCategory] = useState<(typeof QUESTION_CATEGORIES)[number]>(
    QUESTION_CATEGORIES[0],
  );
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const pending = useRef<AbortController | null>(null);
  const snapshotKey = `${selection.event ?? "live"}:${selection.side ?? "after"}`;
  useEffect(() => {
    pending.current?.abort();
    pending.current = null;
    setBusy(false);
    setMessage("");
    return () => pending.current?.abort();
  }, [open, revision, snapshotKey]);
  const interpret = async (text: string, mode: "model" | "example" = "model") => {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setBusy(true);
    setMessage("");
    setQuestion(text);
    try {
      const result = await interpretQuestion(
        text,
        revision,
        selection,
        AbortSignal.any([controller.signal, AbortSignal.timeout(70_000)]),
        mode,
      );
      if (controller.signal.aborted) return;
      if (result.status === "ready") {
        onSelect({ ...result.question, revision: result.revision, snapshotKey });
        onOpenChange(false);
      } else setMessage(result.message);
    } catch (error) {
      if (!controller.signal.aborted)
        setMessage(error instanceof Error ? error.message : "Could not interpret the question.");
    } finally {
      if (pending.current === controller) setBusy(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-auto sm:max-w-3xl">
        <DialogTitle>Questions</DialogTitle>
        <fieldset className="flex flex-wrap gap-2" aria-label="Suggested questions">
          {QUESTION_SUGGESTIONS.map((s) => (
            <Button
              key={s.label}
              type="button"
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => {
                setQuestion(s.question);
                setMessage("");
              }}
              aria-label={`Use ${s.label} question`}
            >
              {s.label}
            </Button>
          ))}
        </fieldset>
        <p className="text-xs text-muted-foreground">
          For Why, What-if and Min-prevention, select Before third delivery or the event's Before
          snapshot.
        </p>
        <form
          className="space-y-2"
          onSubmit={(event) => {
            event.preventDefault();
            void interpret(question);
          }}
        >
          <label className="block space-y-1 text-sm">
            <span>Ask about Nova</span>
            <textarea
              aria-label="Ask about Nova"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              maxLength={2000}
              rows={2}
              placeholder="Why can't Auditor A receive the pending HR message?"
              className="w-full rounded border border-border bg-background p-2"
            />
          </label>
          <Button type="submit" size="sm" disabled={busy || !question.trim()}>
            {busy ? "Interpreting…" : "Interpret question"}
          </Button>
          {message && (
            <p role="status" className="text-sm text-muted-foreground">
              {message}
            </p>
          )}
        </form>
        <div
          role="tablist"
          aria-label="Question categories"
          className="flex overflow-x-auto border-b border-border"
        >
          {QUESTION_CATEGORIES.map((name, i) => (
            <button
              key={name}
              type="button"
              role="tab"
              id={`question-category-${i}`}
              aria-controls="question-list"
              aria-selected={category === name}
              tabIndex={category === name ? 0 : -1}
              onClick={() => setCategory(name)}
              onKeyDown={(event) => {
                const next =
                  event.key === "ArrowRight"
                    ? (i + 1) % QUESTION_CATEGORIES.length
                    : event.key === "ArrowLeft"
                      ? (i + QUESTION_CATEGORIES.length - 1) % QUESTION_CATEGORIES.length
                      : event.key === "Home"
                        ? 0
                        : event.key === "End"
                          ? QUESTION_CATEGORIES.length - 1
                          : undefined;
                if (next === undefined) return;
                event.preventDefault();
                setCategory(QUESTION_CATEGORIES[next]!);
                document.getElementById(`question-category-${next}`)?.focus();
              }}
              className={`whitespace-nowrap px-3 py-2 text-xs ${category === name ? "bg-muted font-medium" : "text-muted-foreground"}`}
            >
              {name}
            </button>
          ))}
        </div>
        <div
          role="tabpanel"
          id="question-list"
          aria-labelledby={`question-category-${QUESTION_CATEGORIES.indexOf(category)}`}
          className="space-y-3"
        >
          {category === "Communication" && (
            <p className="text-xs text-muted-foreground">
              Choose the snapshot before the receive decision.
            </p>
          )}
          {QUESTIONS.filter((q) => q.category === category).map((q) => (
            <div key={q.id} className="flex items-start gap-3 rounded border border-border p-3">
              <div className="min-w-0 flex-1 space-y-2">
                <p className="text-sm">{q.question}</p>
                {"tab" in q && (
                  <details className="text-xs text-muted-foreground">
                    <summary className="cursor-pointer">Query template</summary>
                    <code className="mt-1 block whitespace-pre-wrap break-words">{q.template}</code>
                  </details>
                )}
              </div>
              <Button
                size="sm"
                variant="outline"
                aria-label={`Open question: ${q.question}`}
                disabled={busy}
                onClick={() => void interpret(q.question, "example")}
              >
                Open example
              </Button>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
