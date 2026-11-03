/** Independent executable interpretation of Nova P2/P3; imports no policy rules. */
export function permitted(input: {
  recipient: string;
  known: string[];
  incoming: string[];
  capabilities: string[];
  requirements: [string, string][];
  groups: [string, string][];
}) {
  if (
    input.requirements.some(
      ([tag, capability]) =>
        input.incoming.includes(tag) && !input.capabilities.includes(capability),
    )
  )
    return false;
  if (input.recipient === "board") return true;
  const combined = new Set([...input.known, ...input.incoming]);
  for (const group of new Set(input.groups.map(([, group]) => group))) {
    const tags = new Set(
      input.groups
        .filter(([tag, candidate]) => candidate === group && combined.has(tag))
        .map(([tag]) => tag),
    );
    if (tags.size >= 3) return false;
  }
  return true;
}

export const NOVA_TAGS = ["nova_procurement", "nova_facility", "nova_hiring"];
export const NOVA_GROUPS: [string, string][] = NOVA_TAGS.map((tag) => [tag, "nova"]);
export const NOVA_REQUIREMENTS: [string, string][] = [["nova_hiring", "hr_review"]];
export const subset = (values: string[], mask: number) => values.filter((_, i) => mask & (1 << i));
