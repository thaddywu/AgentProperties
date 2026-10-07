export type QuestionTemplate = {
  id: string;
  category: string;
  question: string;
  template: string;
  tab: "query" | "why" | "what-if" | "minimal" | "speculative";
  scope: string;
  query?: string;
  remove?: string;
};
export const QUESTION_CATEGORIES = [
  "Information flow",
  "Capability",
  "Communication",
  "Provenance",
  "Resource lifecycle",
] as const;
export type QuestionEntry =
  | QuestionTemplate
  | { id: string; category: string; question: string; template: string };
export const QUESTIONS: QuestionEntry[] = [
  {
    id: "sources",
    category: "Information flow",
    question: "Which messages are sources of this information?",
    template: "TrustedSource(M, {tag})",
    tab: "query",
    scope: "board",
    query: "?- TrustedSource(M, nova_hiring).",
  },
  {
    id: "holders",
    category: "Information flow",
    question: "Which agents have received this information?",
    template: "Knows(P, {tag})",
    tab: "query",
    scope: "debug",
    query: "?- Knows(P, nova_hiring).",
  },
  {
    id: "labels",
    category: "Information flow",
    question: "Which tags are attached to this message?",
    template: "Propagated({message}, Tag)",
    tab: "query",
    scope: "hr",
    query: "?- Propagated(mH, Tag).",
  },
  {
    id: "capabilities",
    category: "Capability",
    question: "What permissions does this agent have?",
    template: "HasCap({principal}, Cap)",
    tab: "query",
    scope: "auditor_a",
    query: "?- HasCap(auditor_a, Cap).",
  },
  {
    id: "required",
    category: "Capability",
    question: "What permission is required to receive this information?",
    template: "Requires({tag}, Cap)",
    tab: "query",
    scope: "auditor_a",
    query: "?- Requires(nova_hiring, Cap).",
  },
  {
    id: "missing-permission",
    category: "Capability",
    question: "Which required permissions is this agent missing?",
    template: "Requires({tag}, Cap), not HasCap({principal}, Cap)",
    tab: "query",
    scope: "auditor_b",
    query: "?- Requires(nova_hiring, Cap), not HasCap(auditor_b, Cap).",
  },
  {
    id: "denial",
    category: "Communication",
    question: "Why would this message be blocked?",
    template: "WHY DenyReceive({recipient}, {message})",
    tab: "why",
    scope: "auditor_a",
    query: "DenyReceive(auditor_a, mH)",
  },
  {
    id: "without-receive",
    category: "Communication",
    question: "Would this message still be blocked if we changed these inputs?",
    template: "WHAT-IF(REMOVE, ADD, DenyReceive({recipient}, {message}))",
    tab: "what-if",
    scope: "auditor_a",
    query: "DenyReceive(auditor_a, mH)",
    remove: "Receiver(auditor_a, mF).\nReceived(auditor_a, mF).",
  },
  {
    id: "prevention",
    category: "Communication",
    question: "Which events could we prevent to allow this message?",
    template: "MIN-PREVENT(EVENTS, DenyReceive({recipient}, {message}))",
    tab: "minimal",
    scope: "auditor_a",
    query: "DenyReceive(auditor_a, mH)",
  },
  {
    id: "label-proof",
    category: "Provenance",
    question: "Why does this message carry this information?",
    template: "WHY Propagated({message}, {tag})",
    tab: "why",
    scope: "hr",
    query: "Propagated(mH, nova_hiring)",
  },
  {
    id: "knowledge-proof",
    category: "Provenance",
    question: "Why does this agent know this information?",
    template: "WHY Knows({principal}, {tag})",
    tab: "why",
    scope: "auditor_a",
    query: "Knows(auditor_a, nova_procurement)",
  },
  {
    id: "dependencies",
    category: "Provenance",
    question: "Which earlier messages could have contributed to this message?",
    template: "DependsOn({message}, Min)",
    tab: "query",
    scope: "hr",
    query: "?- DependsOn(mH, Min).",
  },
  {
    id: "resource-state",
    category: "Resource lifecycle",
    question: "What state is this resource in?",
    template: "ResourceState({resource}, State)",
  },
  {
    id: "resource-actions",
    category: "Resource lifecycle",
    question: "Which actions are enabled for this resource in this state?",
    template: "EnabledAction({resource}, {state}, Action)",
  },
  {
    id: "resource-path",
    category: "Resource lifecycle",
    question: "Can this resource reach the target state from this state?",
    template: "ReachableState({resource}, {from}, {target})",
  },
];
