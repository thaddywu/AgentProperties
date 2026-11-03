import { ACTION_PRESET, NAMES, PRINCIPALS } from "./shared.js";

export type QuestionTemplate = {
  id: string;
  category: string;
  question: string;
  template: string;
  tab: "query" | "why" | "what-if" | "minimal" | "speculative";
  scope: string;
  query?: string;
  remove?: string;
  add?: string;
  events?: string;
  actions?: string;
  argumentNotes?: string[];
  parameters?: Record<string, string | string[]>;
  goal?: string;
  basis?: "earlier" | "selected";
  originalQuestion?: string;
  revision?: number;
  snapshotKey?: string;
  interpretationSource?: "model" | "example";
};
export const QUESTION_CATEGORIES = [
  "Information flow",
  "Capability",
  "Communication",
  "Provenance",
] as const;
type Kind = "principal" | "tag" | "message" | "messages" | "routes" | "goalGroup" | "basis";
type Parameters = Record<string, string | string[]>;
export const QUESTION_ROUTES = ACTION_PRESET.split("\n").map((route) => route.replaceAll(" ", ""));
type BoundParameters = Record<
  "principal" | "recipient" | "tag" | "message" | "earlierMessage" | "goalGroup" | "basis",
  string
> & { eventMessages: string[]; routes: string[] };
type Definition = {
  id: string;
  category: string;
  description: string;
  template: string;
  parameters: Record<string, Kind>;
  defaults: Parameters;
  build: (p: BoundParameters) => Omit<QuestionTemplate, "id" | "category" | "template">;
};
const name = (p: string) => NAMES[p] ?? p;
const tagName = (t: string) =>
  ({ nova_hiring: "HR", nova_procurement: "Procurement", nova_facility: "Facility" })[t] ?? t;
// Bound values are validated against snapshot entities before being quoted as constants.
const c = (value: string) => JSON.stringify(value);
const definitions: Definition[] = [
  {
    id: "sources",
    category: "Information flow",
    description: "Find trusted source messages for a tag",
    template: "TrustedSource(M, {tag})",
    parameters: { tag: "tag" },
    defaults: { tag: "nova_hiring" },
    build: ({ tag }) => ({
      question: `Which messages are the original sources of ${tagName(tag)} information?`,
      tab: "query",
      scope: "board",
      query: `?- TrustedSource(M, ${c(tag)}).`,
    }),
  },
  {
    id: "holders",
    category: "Information flow",
    description: "List principals who have successfully received a tag",
    template: "HasReceivedTag(P, {tag})",
    parameters: { tag: "tag" },
    defaults: { tag: "nova_hiring" },
    build: ({ tag }) => ({
      question: `Who has already received ${tagName(tag)} information?`,
      tab: "query",
      scope: "debug",
      query: `?- HasReceivedTag(P, ${c(tag)}).`,
    }),
  },
  {
    id: "labels",
    category: "Information flow",
    description: "List tags carried by a message",
    template: "MessageTag({message}, Tag)",
    parameters: { message: "message" },
    defaults: { message: "mH" },
    build: ({ message }) => ({
      question: `Which information tags does message ${message} carry?`,
      tab: "query",
      scope: "debug",
      query: `?- MessageTag(${c(message)}, Tag).`,
    }),
  },
  {
    id: "capabilities",
    category: "Capability",
    description: "List a principal's permissions, not current delivery eligibility",
    template: "HasCap({principal}, Cap)",
    parameters: { principal: "principal" },
    defaults: { principal: "auditor_a" },
    build: ({ principal }) => ({
      question: `What permissions does ${name(principal)} have?`,
      tab: "query",
      scope: principal,
      query: `?- HasCap(${c(principal)}, Cap).`,
    }),
  },
  {
    id: "required",
    category: "Capability",
    description: "Find permissions required for a tag",
    template: "Requires({tag}, Cap)",
    parameters: { tag: "tag" },
    defaults: { tag: "nova_hiring" },
    build: ({ tag }) => ({
      question: `What permission is required to receive ${tagName(tag)} information?`,
      tab: "query",
      scope: "auditor_a",
      query: `?- Requires(${c(tag)}, Cap).`,
    }),
  },
  {
    id: "missing-permission",
    category: "Capability",
    description: "Find a principal's missing required permissions for a tag",
    template: "Requires({tag}, Cap), not HasCap({principal}, Cap)",
    parameters: { principal: "principal", tag: "tag" },
    defaults: { principal: "auditor_b", tag: "nova_hiring" },
    build: ({ principal, tag }) => ({
      question: `Which permission is ${name(principal)} missing for ${tagName(tag)} information?`,
      tab: "query",
      scope: principal,
      query: `?- Requires(${c(tag)}, Cap), not HasCap(${c(principal)}, Cap).`,
    }),
  },
  {
    id: "denial",
    category: "Communication",
    description: "Explain why a pending message would be blocked for its recipient",
    template: "WHY DenyReceive({recipient}, {message})",
    parameters: { recipient: "principal", message: "message" },
    defaults: { recipient: "auditor_a", message: "mH" },
    build: ({ recipient, message }) => ({
      question: `Why would message ${message} to ${name(recipient)} be blocked?`,
      tab: "why",
      scope: recipient,
      query: `DenyReceive(${c(recipient)}, ${c(message)})`,
    }),
  },
  {
    id: "without-receive",
    category: "Communication",
    description:
      "Would a pending message still be blocked without one earlier successful receipt? Hypothetical only",
    template:
      "WHAT-IF REMOVE Received({recipient}, {earlierMessage}); DenyReceive({recipient}, {message})",
    parameters: { recipient: "principal", message: "message", earlierMessage: "message" },
    defaults: { recipient: "auditor_a", message: "mH", earlierMessage: "mF" },
    build: ({ recipient, message, earlierMessage }) => ({
      question: `Would message ${message} to ${name(recipient)} still be blocked without its earlier receipt of ${earlierMessage}?`,
      tab: "what-if",
      scope: recipient,
      query: `DenyReceive(${c(recipient)}, ${c(message)})`,
      remove: `Received(${c(recipient)}, ${c(earlierMessage)}).`,
      add: "",
      argumentNotes: ["ADD is empty: this template changes only the specified earlier receipt."],
    }),
  },
  {
    id: "prevention",
    category: "Communication",
    description:
      "Find the smallest set of successful receipt events to prevent so a pending message is not blocked. eventMessages is the array of earlier delivered message IDs to consider at recipient; do not supply facts or event names.",
    template: "MIN-PREVENT({eventMessages}, DenyReceive({recipient}, {message}))",
    parameters: { recipient: "principal", message: "message", eventMessages: "messages" },
    defaults: { recipient: "auditor_a", message: "mH", eventMessages: ["mP", "mF"] },
    build: ({ recipient, message, eventMessages }) => ({
      question: `Among ${eventMessages.join(", ")}, which earlier deliveries to ${name(recipient)} should we prevent so message ${message} is not blocked?`,
      tab: "minimal",
      scope: recipient,
      query: `DenyReceive(${c(recipient)}, ${c(message)})`,
      events: eventMessages
        .map((id, i) => `event${i + 1}:\n  Received(${c(recipient)}, ${c(id)}).`)
        .join("\n"),
      argumentNotes: [
        "Each candidate event represents one successful receipt. Search minimizes the number of prevented events.",
      ],
    }),
  },
  {
    id: "label-proof",
    category: "Provenance",
    description: "Explain why a message carries a tag",
    template: "WHY MessageTag({message}, {tag})",
    parameters: { message: "message", tag: "tag" },
    defaults: { message: "mH", tag: "nova_hiring" },
    build: ({ message, tag }) => ({
      question: `Why does message ${message} carry ${tagName(tag)} information?`,
      tab: "why",
      scope: "debug",
      query: `MessageTag(${c(message)}, ${c(tag)})`,
    }),
  },
  {
    id: "knowledge-proof",
    category: "Provenance",
    description: "Explain why a principal is recorded as having successfully received a tag",
    template: "WHY HasReceivedTag({principal}, {tag})",
    parameters: { principal: "principal", tag: "tag" },
    defaults: { principal: "auditor_a", tag: "nova_procurement" },
    build: ({ principal, tag }) => ({
      question: `Why is ${name(principal)} recorded as having received ${tagName(tag)} information?`,
      tab: "why",
      scope: principal,
      query: `HasReceivedTag(${c(principal)}, ${c(tag)})`,
    }),
  },
  {
    id: "dependencies",
    category: "Provenance",
    description: "Find earlier messages that may have contributed information to a message",
    template: "MayDependOn({message}, Min)",
    parameters: { message: "message" },
    defaults: { message: "mH" },
    build: ({ message }) => ({
      question: `Which earlier messages could have contributed to message ${message}?`,
      tab: "query",
      scope: "debug",
      query: `?- MayDependOn(${c(message)}, Min).`,
    }),
  },
  {
    id: "completion",
    category: "Communication",
    description: "Query whether the Nova audit is already complete",
    template: "Finished(Group)",
    parameters: {},
    defaults: {},
    build: () => ({
      question: "Is the Nova audit complete now?",
      tab: "query",
      scope: "debug",
      query: "?- Finished(Group).",
    }),
  },
  {
    id: "planning",
    category: "Communication",
    description:
      "Find a legal sequence reaching Finished(goalGroup). basis is earlier (A has only Procurement) or selected. routes is an array of allowed department->auditor IDs selected from context.routes. Planning does not change the live state.",
    template: "PLAN Finished({goalGroup}) from {basis} using {routes}",
    parameters: { goalGroup: "goalGroup", basis: "basis", routes: "routes" },
    defaults: { goalGroup: "nova", basis: "earlier", routes: QUESTION_ROUTES },
    build: ({ goalGroup, basis, routes }) => ({
      question: `How can we complete ${goalGroup} ${basis === "earlier" ? "from when Auditor A had only Procurement" : "from the selected snapshot"}, using ${routes.join(", ")}?`,
      tab: "speculative",
      scope: "debug",
      goal: `Finished(${c(goalGroup)})`,
      basis: basis as "earlier" | "selected",
      actions: routes.join("\n"),
    }),
  },
];
export const QUESTION_TEMPLATES = definitions.map(({ id, description, parameters }) => ({
  id,
  description,
  parameters,
}));
const build = (d: Definition, parameters: Parameters): QuestionTemplate => ({
  id: d.id,
  category: d.category,
  template: d.template,
  ...d.build(parameters as BoundParameters),
});
export const QUESTIONS = definitions.map((d) => build(d, d.defaults));
export type QuestionEntry = QuestionTemplate;
export type QuestionEntities = {
  tags: string[];
  messages: { id: string; from: string; to: string; status: string }[];
  goalGroups?: string[];
};
export function compileQuestion(
  templateId: string,
  parameters: Parameters,
  context: QuestionEntities,
): QuestionTemplate {
  const d = definitions.find((d) => d.id === templateId);
  if (!d || Object.keys(parameters).sort().join(",") !== Object.keys(d.parameters).sort().join(","))
    throw new Error("Unknown template or missing/extra parameters.");
  for (const [key, kind] of Object.entries(d.parameters)) {
    const value = parameters[key];
    if (kind === "messages" || kind === "routes") {
      const allowed = kind === "messages" ? context.messages.map((m) => m.id) : QUESTION_ROUTES;
      if (
        !Array.isArray(value) ||
        !value.length ||
        value.length > 12 ||
        new Set(value).size !== value.length ||
        value.some((v) => !allowed.includes(v))
      )
        throw new Error(`Select a nonempty list of distinct ${kind} from this application.`);
      continue;
    }
    if (typeof value !== "string") throw new Error("Missing string parameter.");
    const valid =
      kind === "principal"
        ? PRINCIPALS.some((p) => p === value)
        : kind === "tag"
          ? context.tags.includes(value)
          : kind === "goalGroup"
            ? context.goalGroups?.includes(value)
            : kind === "basis"
              ? ["earlier", "selected"].includes(value)
              : context.messages.some((m) => m.id === value);
    if (!valid) throw new Error(`Unknown ${kind}; select an entity in this snapshot.`);
  }
  if (["denial", "without-receive", "prevention"].includes(d.id)) {
    const recipient = parameters.recipient ?? "auditor_a",
      message = parameters.message ?? "mH";
    if (
      !context.messages.some(
        (m) => m.id === message && m.to === recipient && m.status === "pending",
      )
    )
      throw new Error("Select the snapshot with that delivery pending at its recipient.");
  }
  if (
    d.id === "without-receive" &&
    !context.messages.some(
      (m) =>
        m.id === parameters.earlierMessage &&
        m.to === parameters.recipient &&
        m.status === "delivered",
    )
  )
    throw new Error(
      "The earlier message was not successfully delivered to this recipient in this snapshot.",
    );
  if (
    d.id === "prevention" &&
    !(parameters.eventMessages as string[]).every((id) =>
      context.messages.some(
        (m) => m.id === id && m.to === parameters.recipient && m.status === "delivered",
      ),
    )
  )
    throw new Error("Every candidate must be a successful earlier delivery to this recipient.");
  if (
    d.id === "planning" &&
    parameters.basis === "selected" &&
    context.messages.some((m) => m.status === "pending")
  )
    throw new Error(
      "Resolve pending deliveries or choose the starting state before the second delivery.",
    );

  return { ...build(d, parameters), parameters };
}
export function exampleIntent(id: string) {
  const d = definitions.find((d) => d.id === id);
  if (!d) throw new Error("Unknown question example.");
  return { templateId: d.id, parameters: { ...d.defaults } };
}

/** Fill-only suggestions: clicking these never calls the model or changes the selected snapshot. */
export const QUESTION_SUGGESTIONS = [
  { label: "Why", question: "Why would Auditor A's pending HR message mH be blocked?" },
  {
    label: "What-if",
    question:
      "If Auditor A had not received Facility message mF, would HR message mH still be blocked? Leave all other inputs unchanged.",
  },
  {
    label: "Min-prevention",
    question:
      "Among Auditor A's earlier Procurement (mP) and Facility (mF) deliveries, what is the smallest set to prevent so HR message mH would not be blocked?",
  },
  {
    label: "Planning",
    question:
      "Starting when Auditor A had only Procurement, can we complete the Nova audit by sending Facility and HR to either auditor? Show a legal sequence.",
  },
];
