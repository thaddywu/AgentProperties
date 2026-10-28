import type { PolicyBundle } from "@rakazo/policy-runtime/application";
import { createPolicySession } from "@rakazo/policy-runtime/application";
import type { PolicyFact } from "@rakazo/policy-runtime/datalog";

/** Everything here is app-owned; the shared runtime knows neither documents nor Nova. */
export function createDocumentService(
  binding: unknown,
  bundle: PolicyBundle,
  inputs: PolicyFact[],
  documents: Record<string, string>,
) {
  const session = createPolicySession(binding, bundle, inputs);
  const contents = new Map(Object.entries(documents));
  let payloadReads = 0;
  return {
    session,
    get payloadReads() {
      return payloadReads;
    },
    // Actor comes from authentication in a deployed adapter, never an arbitrary client parameter.
    read(actor: string, document: string) {
      return session.execute({ actor, action: "read", resource: document }, async () => {
        payloadReads++;
        if (!contents.has(document)) throw new Error("Document does not exist in the service.");
        return contents.get(document)!;
      }, [{ predicate: "Read", args: [actor, document] }]);
    },
  };
}
