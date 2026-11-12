import type {
  ReviewFeedback,
  ReviewWorkspace,
  TranslationReview,
} from "@rakazo/policy-translation/review-contract";

export async function reviewRequest(
  body: { operation: "load" } | { operation: "translate"; policyText: string },
): Promise<ReviewWorkspace> {
  const response = await fetch("/policy-review-api", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok || !data.result) throw new Error(data.error ?? "Could not load the review.");
  return data.result;
}

export const storageKey = (review: TranslationReview) => `policy-review:v1:${review.id}`;
export const draftKey = "policy-review:v1:draft";

/** Restoring a local draft never sends its rules or feedback back as trusted server input. */
export function readDraft(
  raw: string | null,
  reference: TranslationReview,
): TranslationReview | undefined {
  if (!raw || raw.length > 2_000_000) return;
  try {
    const r = JSON.parse(raw);
    const text = (v: unknown, max = 24000) => typeof v === "string" && v.length <= max;
    const strings = (v: unknown) => Array.isArray(v) && v.length <= 200 && v.every((s) => text(s));
    if (
      r?.version !== 1 ||
      r.origin !== "model" ||
      r.application !== reference.application ||
      r.contractHash !== reference.contractHash ||
      !text(r.id, 64) ||
      !/^[a-f0-9]{64}$/.test(r.id) ||
      !text(r.sourceText) ||
      !text(r.createdAt, 100) ||
      r.validation !== "static-only" ||
      !Array.isArray(r.policies) ||
      !r.policies.length ||
      r.policies.length > 100 ||
      !Array.isArray(r.requirements) ||
      r.requirements.length > 200 ||
      !Array.isArray(r.rules) ||
      r.rules.length > 99 ||
      !Array.isArray(r.behaviors) ||
      r.behaviors.length > 300 ||
      !r.policies.every((p: { id: string; text: string }) => p && text(p.id, 64) && text(p.text)) ||
      !r.rules.every(
        (rule: { id: string; datalog: string }) => rule && text(rule.id, 64) && text(rule.datalog),
      )
    )
      return;
    for (const requirement of r.requirements) {
      const policy = r.policies.find((p: { id: string }) => p.id === requirement?.policyId);
      if (
        !policy ||
        !text(requirement.id, 64) ||
        !text(requirement.statement) ||
        !strings(requirement.assumptions) ||
        !Number.isInteger(requirement.start) ||
        !Number.isInteger(requirement.end) ||
        requirement.start < 0 ||
        requirement.start >= requirement.end ||
        requirement.end > policy.text.length ||
        !["datalog", "mechanism", "adapter", "unsupported", "ambiguous"].includes(
          requirement.implementation,
        ) ||
        !["equivalent", "stronger", "weaker", "partial", "unresolved"].includes(
          requirement.relation,
        )
      )
        return;
    }
    for (const behavior of r.behaviors) {
      if (
        !behavior ||
        !text(behavior.id, 100) ||
        !text(behavior.summary) ||
        !strings(behavior.conditions) ||
        !strings(behavior.requirementIds) ||
        !strings(behavior.ruleIds) ||
        !["rule", "integration", "gap"].includes(behavior.kind) ||
        (behavior.question !== undefined && !text(behavior.question)) ||
        !Array.isArray(behavior.evidence) ||
        behavior.evidence.length > 64 ||
        !behavior.evidence.every(
          (e: { name: string; meaning: string }) => e && text(e.name, 100) && text(e.meaning),
        ) ||
        behavior.requirementIds.some(
          (id: string) => !r.requirements.some((q: { id: string }) => q.id === id),
        ) ||
        behavior.ruleIds.some(
          (id: string) => !r.rules.some((rule: { id: string }) => rule.id === id),
        )
      )
        return;
    }
    return r as TranslationReview;
  } catch {
    return;
  }
}

export function readFeedback(
  raw: string | null,
  review: TranslationReview,
): Record<string, ReviewFeedback> {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    const result: Record<string, ReviewFeedback> = {};
    for (const behavior of review.behaviors) {
      const entry = parsed[behavior.id];
      if (
        !entry ||
        typeof entry !== "object" ||
        typeof entry.note !== "string" ||
        entry.note.length > 4000
      )
        continue;
      if (entry.rating !== undefined && !["matches", "different", "unsure"].includes(entry.rating))
        continue;
      if (
        entry.difference !== undefined &&
        !["missing", "stricter", "weaker", "meaning"].includes(entry.difference)
      )
        continue;
      if (entry.expectation !== undefined && !["yes", "no", "unsure"].includes(entry.expectation))
        continue;
      result[behavior.id] = {
        rating: entry.rating,
        difference: entry.difference,
        expectation: entry.expectation,
        note: entry.note,
      };
    }
    return result;
  } catch {
    return {};
  }
}

export function exportReview(review: TranslationReview, feedback: Record<string, ReviewFeedback>) {
  return {
    version: 1,
    exportedAt: new Date().toISOString(),
    review,
    feedback: readFeedback(JSON.stringify(feedback), review),
    scope:
      "Human assessment of meaning. Not developer approval, runtime installation or proof of equivalence.",
  };
}
