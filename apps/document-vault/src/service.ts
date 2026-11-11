import { createActionPort } from "@rakazo/policy-runtime/action-port";
import type { PolicyBundle } from "@rakazo/policy-runtime/application";
import type { PolicyFact } from "@rakazo/policy-runtime/datalog";

/** Everything here is app-owned; the shared runtime knows neither documents nor Nova. */
export function createDocumentService(
  binding: unknown,
  bundle: PolicyBundle,
  inputs: PolicyFact[],
  documents: Record<string, string>,
) {
  const contents = new Map(Object.entries(documents));
  let payloadReads = 0;
  const port = createActionPort({
    binding,
    bundle,
    inputs,
    operations: [
      {
        action: "read",
        observations: ["Read"],
        execute: async ({ request }) => {
          const resource = request.resource ?? request.parameters?.resource;
          if (!resource || !contents.has(resource))
            return { status: "not_applied", reason: "Document does not exist." };
          payloadReads++;
          return {
            status: "applied",
            value: contents.get(resource)!,
            observations: [{ predicate: "Read", args: [request.actor, resource] }],
          };
        },
      },
    ],
  });
  return {
    session: port,
    get payloadReads() {
      return payloadReads;
    },
    // Actor comes from authentication in a deployed adapter, never an arbitrary client parameter.
    read(actor: string, document: string) {
      return port.bind(actor).execute("read", document);
    },
  };
}
