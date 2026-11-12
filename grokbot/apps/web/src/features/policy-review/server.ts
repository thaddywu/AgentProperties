import type { ReviewApplication } from "@rakazo/policy-translation/review";
import { referenceReview, translateForReview } from "@rakazo/policy-translation/review";

/** Local composition boundary; clients cannot choose files, bindings, model credentials or code. */
export function policyReviewHandler(
  load: () => Promise<ReviewApplication>,
  generate?: (prompt: string) => Promise<string>,
) {
  let busy = false;
  return async (body: unknown) => {
    if (!body || typeof body !== "object" || Array.isArray(body))
      throw new Error("Invalid policy review request.");
    const value = body as Record<string, unknown>;
    if (value.operation === "load" && Object.keys(value).length === 1)
      return { modelAvailable: !!generate, review: referenceReview(await load()) };
    if (
      value.operation !== "translate" ||
      Object.keys(value).some((key) => !["operation", "policyText"].includes(key)) ||
      typeof value.policyText !== "string" ||
      !value.policyText.trim() ||
      value.policyText.length > 24_000
    )
      throw new Error("Provide numbered policies of up to 24,000 characters.");
    if (!generate)
      throw new Error(
        "Connect a model on the server to translate edits. The reference is available to review.",
      );
    if (busy) throw new Error("A translation is already running. Please wait.");
    busy = true;
    try {
      // Provider errors may contain endpoints or credentials. Keep them outside the HTTP response.
      const guardedGenerate = async (prompt: string) => {
        try {
          return await generate(prompt);
        } catch {
          throw new Error(
            "The model could not finish this translation. Check the server connection and retry.",
          );
        }
      };
      return {
        modelAvailable: true,
        review: await translateForReview(await load(), value.policyText, guardedGenerate),
      };
    } finally {
      busy = false;
    }
  };
}
