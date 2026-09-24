import type { PolicyObservation, PolicyPrincipal } from "@rakazo/contracts";
import { formatFact } from "@rakazo/core";
import { Button, Popover, PopoverContent, PopoverTrigger } from "@rakazo/ui-web";
import { useState } from "react";
import { usePolicyMode } from "./PolicyWorkspace";

export function policyHoverText(policy?: PolicyObservation) {
  if (!policy) return undefined;
  return [
    policy.event.messageId,
    ...policy.facts.map(formatFact),
    policy.facts.length ? undefined : "No restricted tags",
  ]
    .filter(Boolean)
    .join("\n");
}
export function PolicyMessageDetails({ policy }: { policy?: PolicyObservation }) {
  const enabled = usePolicyMode();
  if (!enabled || !policy) return null;
  return <Details policy={policy} />;
}
function Details({ policy }: { policy: PolicyObservation }) {
  const [principal, setPrincipal] = useState<PolicyPrincipal>(policy.event.actor);
  const [side, setSide] = useState<"before" | "after">("after");
  const store = policy.event[side][principal];
  const denied = policy.event.decision === "deny";
  return (
    <span className="ml-6 mt-1 inline-flex items-center md:ml-0" data-testid="policy-observation">
      <Popover>
        <PopoverTrigger
          aria-label={`Local store after event ${policy.event.seq}`}
          title={policyHoverText(policy)}
          className="grid size-11 place-items-center rounded-full hover:bg-muted focus-visible:outline md:size-6"
        >
          <span
            className={`size-1.5 rounded-full ${denied ? "bg-destructive" : "bg-muted-foreground"}`}
          />
        </PopoverTrigger>
        <PopoverContent
          className="max-h-[70vh] w-[min(420px,90vw)] overflow-auto text-xs"
          align="start"
        >
          <div className="mb-3 flex items-center justify-between">
            <strong>Local store · Event {policy.event.seq}</strong>
            <span>{policy.event.kind}</span>
          </div>
          {policy.event.messageId && (
            <code className="mb-3 block break-all">{policy.event.messageId}</code>
          )}
          <div className="mb-3">
            <strong>Attached tags</strong>
            {policy.facts.length ? (
              policy.facts.map((f) => (
                <code className="mt-1 block break-all" key={formatFact(f)}>
                  {formatFact(f)}
                </code>
              ))
            ) : (
              <p className="mt-1 text-muted-foreground">None</p>
            )}
          </div>
          {policy.event.decision && (
            <p className={denied ? "mb-3 text-destructive" : "mb-3"}>
              {denied
                ? `Denied · ${policy.event.rules.join(", ")} · receiver unchanged`
                : "Delivered"}
            </p>
          )}
          <select
            aria-label="Snapshot principal"
            value={principal}
            onChange={(e) => setPrincipal(e.target.value as PolicyPrincipal)}
            className="mb-2 w-full rounded border border-border bg-background p-2"
          >
            {Object.keys(policy.event.after).map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
          <div className="mb-3 flex gap-1">
            {(["before", "after"] as const).map((value) => (
              <Button
                key={value}
                size="sm"
                variant={side === value ? "secondary" : "ghost"}
                onClick={() => setSide(value)}
              >
                {value === "before" ? "Before" : "After"}
              </Button>
            ))}
          </div>
          <div data-testid="policy-local-store">
            {["Knows", "Received", "Carries", "DerivedFrom"].map((predicate) => (
              <details key={predicate} open={predicate === "Knows"} className="mb-3">
                <summary className="cursor-pointer">
                  {predicate} · {store.facts.filter((f) => f.predicate === predicate).length}
                </summary>
                {store.facts
                  .filter((f) => f.predicate === predicate)
                  .map((f) => (
                    <code key={formatFact(f)} className="mt-1 block break-all rounded bg-muted p-2">
                      {formatFact(f)}
                    </code>
                  ))}
              </details>
            ))}
          </div>
          <details>
            <summary className="cursor-pointer">Artifacts · {store.artifacts.length}</summary>
            {store.artifacts.map((id) => (
              <details key={id} className="mt-2">
                <summary className="cursor-pointer break-all">{id}</summary>
                <p className="mt-1 whitespace-pre-wrap">{policy.artifacts[id]?.text}</p>
              </details>
            ))}
          </details>
          {denied && (
            <details className="mt-3">
              <summary className="cursor-pointer">Rule witnesses</summary>
              {policy.event.witnesses.map((f, i) => (
                <code className="mt-1 block break-all" key={i}>
                  {formatFact(f)}
                </code>
              ))}
            </details>
          )}
        </PopoverContent>
      </Popover>
      <span
        className="pointer-events-none absolute right-0 bottom-full z-30 hidden max-w-sm whitespace-pre-wrap rounded border border-border bg-popover p-2 text-[11px] text-popover-foreground shadow-sm group-hover/message:block"
        data-testid="policy-hover-tags"
      >
        {policyHoverText(policy)}
      </span>
    </span>
  );
}
