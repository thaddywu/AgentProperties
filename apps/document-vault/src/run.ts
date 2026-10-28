import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parseArgs } from "node:util";
import type { PolicyBundle } from "@rakazo/policy-runtime/application";
import type { PolicyFact } from "@rakazo/policy-runtime/datalog";
import { createDocumentService } from "./service.js";

const { values } = parseArgs({ options: { bundle: { type: "string" } } });
if (!values.bundle) throw new Error("Pass --bundle <translated policy-bundle.json>.");
const bundle = JSON.parse(readFileSync(values.bundle, "utf8")) as PolicyBundle;
const binding: unknown = JSON.parse(
  readFileSync(new URL("../runtime.json", import.meta.url), "utf8"),
);
const inputs: PolicyFact[] = [
  { predicate: "Actor", args: ["visitor"] },
  { predicate: "Actor", args: ["reviewer-a"] },
  { predicate: "Actor", args: ["suspended-reader"] },
  { predicate: "Public", args: ["guide"] },
  { predicate: "Confidential", args: ["draft"] },
  { predicate: "Role", args: ["reviewer-a", "reviewer"] },
  { predicate: "Reader", args: ["reviewer-a", "draft"] },
  { predicate: "Suspended", args: ["suspended-reader"] },
];
const service = createDocumentService(binding, bundle, inputs, {
  guide: "Public guide body.",
  draft: "Synthetic confidential draft body.",
});
const publicRead = await service.read("visitor", "guide");
const refused = await service.read("visitor", "draft");
const permitted = await service.read("reviewer-a", "draft");
const suspended = await service.read("suspended-reader", "guide");
assert(publicRead.allowed && permitted.allowed);
assert(!refused.allowed && !suspended.allowed);
assert(!("value" in refused) && !("value" in suspended));
assert.equal(service.payloadReads, 2);
assert.equal(service.session.snapshot().filter((fact) => fact.predicate === "Read").length, 2);
const accessible = service.session.query("?- Accessible(A, D).");
assert.deepEqual(accessible.rows.map((row) => row.join(":")).sort(), [
  "reviewer-a:draft",
  "reviewer-a:guide",
  "visitor:guide",
]);
const explanation = service.session.why({ predicate: "Accessible", args: ["reviewer-a", "draft"] });
assert(explanation?.rule);
const hypothetical = service.session.whatIf(
  { actor: "visitor", action: "read", resource: "draft" },
  [
    ...inputs,
    { predicate: "Role", args: ["visitor", "reviewer"] },
    { predicate: "Reader", args: ["visitor", "draft"] },
  ],
);
assert(hypothetical.allowed);
assert(!service.session.check({ actor: "visitor", action: "read", resource: "draft" }).allowed);
console.log(
  JSON.stringify(
    {
      policyHash: service.session.policyHash,
      publicRead: publicRead.allowed,
      unauthorizedRead: refused.allowed,
      qualifiedRead: permitted.allowed,
      suspendedRead: suspended.allowed,
      payloadReads: service.payloadReads,
      successfulReadRecords: 2,
      accessible,
      explanation,
      hypotheticalQualifiedRead: hypothetical.allowed,
      hypotheticalCommitted: false,
    },
    null,
    2,
  ),
);
