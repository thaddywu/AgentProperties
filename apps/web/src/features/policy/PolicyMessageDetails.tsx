import type { PolicyObservation } from "@rakazo/contracts";
import { formatFact } from "@rakazo/core";
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
  return (
    <span data-testid="policy-observation">
      <span
        className="pointer-events-none absolute right-0 bottom-full z-30 hidden max-w-sm whitespace-pre-wrap rounded border border-border bg-popover p-2 text-[11px] text-popover-foreground shadow-sm group-hover/message:block"
        data-testid="policy-hover-tags"
      >
        {policyHoverText(policy)}
      </span>
    </span>
  );
}
