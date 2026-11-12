import { fileURLToPath } from "node:url";
import { loadReviewApplication, referenceReview } from "@rakazo/policy-translation/review";
import { expect, it } from "vitest";
import { exportReview, readDraft, readFeedback, storageKey } from "./client";

it("pins exported judgments to the exact review and discards malformed or unrelated saved feedback", async () => {
  const review = referenceReview(
    await loadReviewApplication(
      fileURLToPath(new URL("../../../../../../apps/labcluster-port", import.meta.url)),
    ),
  );
  const feedback = readFeedback(
    JSON.stringify({
      completion: {
        rating: "different",
        difference: "stricter",
        note: "Failed runs should count as ended.",
        expectation: "yes",
      },
      quotas: { rating: "invented", note: "" },
      unknown: { rating: "matches", note: "" },
    }),
    review,
  );
  expect(Object.keys(feedback)).toEqual(["completion"]);
  expect(readFeedback("not json", review)).toEqual({});
  const report = exportReview(review, feedback);
  expect(report.review.id).toBe(review.id);
  expect(report.feedback.completion?.expectation).toBe("yes");
  expect(storageKey({ ...review, id: "changed" })).not.toBe(storageKey(review));
  const draft = { ...review, origin: "model" };
  expect(readDraft(JSON.stringify(draft), review)).toEqual(draft);
  expect(readDraft(JSON.stringify({ ...draft, contractHash: "stale" }), review)).toBeUndefined();
  expect(
    readDraft(JSON.stringify({ ...draft, behaviors: [{ summary: "broken" }] }), review),
  ).toBeUndefined();
});
