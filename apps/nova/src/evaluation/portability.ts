import { compileApplicationPolicy, createPolicySession } from "@rakazo/policy-runtime/application";
import type { RuntimeBinding } from "@rakazo/policy-runtime/binding";
import type { PolicyFact } from "@rakazo/policy-runtime/datalog";

const f = (predicate: string, ...args: string[]): PolicyFact => ({ predicate, args });
const inputs = [
  f("Author", "draft", "writer"),
  f("Reviewer", "reviewer"),
  f("Publisher", "publisher"),
];
const request = (actor: string, action: string) => ({ actor, action, resource: "draft" });
const binding: RuntimeBinding = {
  version: 1,
  id: "approval-pilot",
  context:
    "Synthetic independent approval service. Authentication, roles and document authorship are trusted adapter inputs. Approval and publication are observations committed after successful callbacks. No Nova vocabulary or message protocol is used.",
  predicates: Object.fromEntries(
    [
      ["Author", "input", ["Document", "Actor"]],
      ["Reviewer", "input", ["Actor"]],
      ["Publisher", "input", ["Actor"]],
      ["Approved", "input", ["Document", "Reviewer"]],
      ["Published", "input", ["Document"]],
      ["Attempt", "input", ["RequestId", "Actor", "Action", "Resource"]],
      ["Permit", "derived", ["RequestId"]],
      ["Refuse", "derived", ["RequestId", "Reason"]],
    ].map(([name, kind, args]) => [
      name,
      { kind, args, meaning: `Trusted approval-service relation ${name}.` },
    ]),
  ) as RuntimeBinding["predicates"],
  decision: { request: "Attempt", allow: "Permit", deny: "Refuse" },
  tests: [
    {
      name: "independent-reviewer",
      inputs,
      request: request("reviewer", "approve"),
      allowed: true,
    },
    {
      name: "author-cannot-approve",
      inputs: [...inputs, f("Reviewer", "writer")],
      request: request("writer", "approve"),
      allowed: false,
    },
    { name: "approval-required", inputs, request: request("publisher", "publish"), allowed: false },
    {
      name: "approved-publication",
      inputs: [...inputs, f("Approved", "draft", "reviewer")],
      request: request("publisher", "publish"),
      allowed: true,
    },
    {
      name: "publish-once",
      inputs: [...inputs, f("Approved", "draft", "reviewer"), f("Published", "draft")],
      request: request("publisher", "publish"),
      allowed: false,
    },
  ],
};
const source = `
Permit(R) :- Attempt(R, A, "approve", D), Reviewer(A), Author(D, Owner), A != Owner.
Permit(R) :- Attempt(R, A, "publish", D), Publisher(A), Author(D, Owner), Approved(D, Reviewer), not Published(D).
Permit(R) :- Attempt(R, A, "dual_publish", D), Publisher(A), Author(D, Owner), Approved(D, X), Approved(D, Y), Reviewer(X), Reviewer(Y), X != Y, not Published(D).
Refuse(R, "author_review") :- Attempt(R, A, "approve", D), Author(D, A).
Refuse(R, "already_published") :- Attempt(R, A, "publish", D), Published(D).
`;

/** An actual new adapter exercise, with handwritten policy to isolate porting from translation. */
export async function portabilityPilot() {
  const bundle = compileApplicationPolicy(binding, source);
  const session = createPolicySession(binding, bundle, [...inputs, f("Reviewer", "writer")]);
  let effects = 0;
  const effect = async () => ++effects;
  const early = await session.execute(request("publisher", "publish"), effect);
  const selfReview = await session.execute(request("writer", "approve"), effect);
  const review = await session.execute(request("reviewer", "approve"), effect, [
    f("Approved", "draft", "reviewer"),
  ]);
  const concurrent = await Promise.all(
    [1, 2].map(() =>
      session.execute(request("publisher", "publish"), effect, [f("Published", "draft")]),
    ),
  );
  const ordered = {
    early: early.allowed,
    selfReview: selfReview.allowed,
    review: review.allowed,
    concurrent: concurrent.map((r) => r.allowed),
    effects,
  };

  // Document the existing cross-session boundary using two adapters sharing one fake store.
  const approved = [...inputs, f("Approved", "draft", "reviewer")];
  const dualInputs = [...approved, f("Reviewer", "second_reviewer")];
  const dual = createPolicySession(binding, bundle, dualInputs);
  const withOneApproval = dual.check(request("publisher", "dual_publish")).allowed;
  await dual.replaceInputs([...dualInputs, f("Approved", "draft", "second_reviewer")]);
  const withTwoApprovals = await dual.execute(
    request("publisher", "dual_publish"),
    async () => "published",
    [f("Published", "draft")],
  );
  const workers = [
    createPolicySession(binding, bundle, approved),
    createPolicySession(binding, bundle, approved),
  ];
  let sharedExternalPublications = 0;
  await Promise.all(
    workers.map((worker) =>
      worker.execute(request("publisher", "publish"), async () => ++sharedExternalPublications, [
        f("Published", "draft"),
      ]),
    ),
  );

  const failed = createPolicySession(binding, bundle, approved);
  let irreversibleEffects = 0;
  let failureObserved = false;
  try {
    await failed.execute(request("publisher", "publish"), async () => {
      irreversibleEffects++;
      throw new Error("Synthetic failure after external effect.");
    }, [f("Published", "draft")]);
  } catch {
    failureObserved = true;
  }
  return {
    policyOrigin: "handwritten independent adapter pilot, not model translation",
    runtimeFilesChanged: 0,
    acceptanceCases: binding.tests.length,
    ordered,
    sameSessionProtected:
      !early.allowed &&
      !selfReview.allowed &&
      review.allowed &&
      concurrent.filter((r) => r.allowed).length === 1 &&
      effects === 2,
    crossSession: { sharedExternalPublications, coordinated: sharedExternalPublications === 1 },
    dualApproval: { withOneApproval, withTwoApprovals: withTwoApprovals.allowed },
    callbackFailure: {
      failureObserved,
      irreversibleEffects,
      committedPublications: failed.snapshot().filter((f) => f.predicate === "Published").length,
    },
    inspection: {
      published: session.query("?- Published(D).").rows,
      denialExplained: session
        .check(request("publisher", "publish"))
        .evidence.some((proof) => proof.rule !== undefined),
      hypotheticalUnpublished: session.whatIf(request("publisher", "publish"), approved).allowed,
      actualStillDenied: !session.check(request("publisher", "publish")).allowed,
    },
  };
}
