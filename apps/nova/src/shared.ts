export const PRINCIPALS = [
  "board",
  "procurement",
  "facility",
  "hr",
  "auditor_a",
  "auditor_b",
] as const;
export const NAMES: Record<string, string> = {
  board: "Executive Board",
  procurement: "Procurement",
  facility: "Facility",
  hr: "HR / Hiring",
  auditor_a: "Auditor A",
  auditor_b: "Auditor B",
};
export const PREVENTABLE_PRESET = `eP:\n  Receiver(auditor_a, mP).\n  Received(auditor_a, mP).\neF:\n  Receiver(auditor_a, mF).\n  Received(auditor_a, mF).`;
export const ACTION_PRESET = ["procurement", "facility", "hr"]
  .flatMap((sender) => ["auditor_a", "auditor_b"].map((receiver) => `${sender} -> ${receiver}`))
  .join("\n");
