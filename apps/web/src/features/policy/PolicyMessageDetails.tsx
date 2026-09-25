import type { PolicyObservation } from "@rakazo/contracts";
import { formatFact } from "@rakazo/core";
import { useStoreInspection } from "./PolicyStoreInspector";
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
  const inspect = useStoreInspection();
  if (!enabled || !policy) return null;
  return (
    <span className="ml-6 mt-1 inline-flex items-center md:ml-0" data-testid="policy-observation">
      <button
        type="button"
        aria-label={`Local store after event ${policy.event.seq}`}
        title={policyHoverText(policy)}
        onClick={() => inspect(policy)}
        className="grid size-11 place-items-center rounded-full hover:bg-muted focus-visible:outline md:size-6"
      >
        <span
          className={`size-1.5 rounded-full ${policy.event.decision === "deny" ? "bg-destructive" : "bg-muted-foreground"}`}
        />
      </button>
      <span
        className="pointer-events-none absolute right-0 bottom-full z-30 hidden max-w-sm whitespace-pre-wrap rounded border border-border bg-popover p-2 text-[11px] text-popover-foreground shadow-sm group-hover/message:block"
        data-testid="policy-hover-tags"
      >
        {policyHoverText(policy)}
      </span>
    </span>
  );
}
