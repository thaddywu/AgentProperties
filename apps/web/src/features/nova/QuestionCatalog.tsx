import type { QuestionTemplate } from "@rakazo/core/policy/reasoning/questions";
import { QUESTION_CATEGORIES, QUESTIONS } from "@rakazo/core/policy/reasoning/questions";
import { Button, Dialog, DialogContent, DialogTitle } from "@rakazo/ui-web";
import { useState } from "react";

export function QuestionCatalog({
  open,
  onOpenChange,
  onSelect,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelect: (question: QuestionTemplate) => void;
}) {
  const [category, setCategory] = useState<(typeof QUESTION_CATEGORIES)[number]>(
    QUESTION_CATEGORIES[0],
  );
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-auto sm:max-w-3xl">
        <DialogTitle>Questions</DialogTitle>
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
          {category === "Resource lifecycle" && (
            <p className="text-xs text-muted-foreground">
              General templates. No resource workflow is connected to Nova.
            </p>
          )}
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
              {"tab" in q ? (
                <Button
                  size="sm"
                  variant="outline"
                  aria-label={`Open question: ${q.question}`}
                  onClick={() => {
                    onSelect(q);
                    onOpenChange(false);
                  }}
                >
                  Open example
                </Button>
              ) : (
                <code className="max-w-[50%] break-words text-xs text-muted-foreground">
                  {q.template}
                </code>
              )}
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
