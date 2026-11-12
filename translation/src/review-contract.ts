/** Browser-safe review data. A review is evidence of human intent, never installation approval. */
export type ReviewRequirement = {
  id: string;
  policyId: string;
  start: number;
  end: number;
  statement: string;
  implementation: "datalog" | "mechanism" | "adapter" | "unsupported" | "ambiguous";
  relation: "equivalent" | "stronger" | "weaker" | "partial" | "unresolved";
  assumptions: string[];
};

export type ReviewBehavior = {
  id: string;
  requirementIds: string[];
  ruleIds: string[];
  kind: "rule" | "integration" | "gap";
  summary: string;
  conditions: string[];
  question?: string;
  evidence: { name: string; meaning: string }[];
};

export type TranslationReview = {
  version: 1;
  id: string;
  application: string;
  origin: "reference" | "model";
  createdAt: string;
  sourceText: string;
  contractHash: string;
  policies: { id: string; text: string }[];
  requirements: ReviewRequirement[];
  rules: { id: string; datalog: string }[];
  behaviors: ReviewBehavior[];
  validation: "static-only";
  /** Unmapped source text is not evidence that the framework cannot support it. */
  omittedRequirementIds: string[];
  generationAttempts: { stage: string; attempt: number; validationError?: string }[];
};

export type ReviewFeedback = {
  rating?: "matches" | "different" | "unsure";
  difference?: "missing" | "stricter" | "weaker" | "meaning";
  note: string;
  expectation?: "yes" | "no" | "unsure";
};

export type ReviewWorkspace = {
  modelAvailable: boolean;
  review: TranslationReview;
};
