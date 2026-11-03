import type { PolicyReview } from "@rakazo/nova/translation-review";
import { useState } from "react";

export function TranslationComparison({
  rows,
  historical = false,
}: {
  rows: PolicyReview["correspondence"];
  historical?: boolean;
}) {
  const [selected, setSelected] = useState("P3");
  const row = rows.find((item) => item.id === selected) ?? rows[0];
  if (!row) return null;
  return (
    <section className="space-y-4" aria-label="Policy comparison">
      <label className="flex flex-wrap items-center gap-2 text-xs font-medium">
        Policy
        <select
          aria-label="Compare policy"
          value={row.id}
          onChange={(event) => setSelected(event.target.value)}
          className="min-w-0 max-w-full rounded border border-border bg-background p-2 text-xs"
        >
          {rows.map((item) => (
            <option key={item.id} value={item.id}>
              {item.id} · {item.title}
            </option>
          ))}
        </select>
      </label>
      <blockquote className="border-l-2 border-border pl-3 text-sm leading-relaxed">
        {row.source}
      </blockquote>
      {!row.inputMatchesReference && (
        <details className="text-xs">
          <summary>Input differs from the current Nova reference</summary>
          <p className="mt-2">{row.referenceSource}</p>
        </details>
      )}
      <div className="grid min-w-0 gap-4 md:grid-cols-2">
        <section
          aria-label="Reference rules"
          className="min-w-0 space-y-3 rounded border border-border p-4"
        >
          <h3 className="text-sm font-medium">
            {historical ? "Reference (historical)" : "Reference"}
          </h3>
          <pre className="whitespace-pre-wrap break-words text-xs leading-relaxed">
            {row.golden || "No reference rules for this policy."}
          </pre>
          <details className="text-xs">
            <summary className="cursor-pointer font-medium">Runtime / protocol support</summary>
            <p className="mt-2 leading-relaxed">{row.protocol}</p>
          </details>
        </section>
        <section
          aria-label="Generated rules"
          className="min-w-0 space-y-3 rounded border border-border p-4"
        >
          <h3 className="text-sm font-medium">Generated</h3>
          {row.basis === "builtin" ? (
            <p className="text-sm text-muted-foreground">
              Uses the fixed runtime rules and protocol. No additional rules generated.
            </p>
          ) : (
            <pre className="whitespace-pre-wrap break-words text-xs leading-relaxed">
              {row.generated}
            </pre>
          )}
          <details className="text-xs">
            <summary className="cursor-pointer font-medium">Model explanation</summary>
            <p className="mt-2 leading-relaxed">{row.notes}</p>
          </details>
        </section>
      </div>
    </section>
  );
}
