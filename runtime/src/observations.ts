import type { PolicyFact } from "./datalog.js";

/** A complete replacement for its registered producer's relations within one policy scope. */
export type ObservationSnapshot = {
  version: string;
  complete: boolean;
  facts: PolicyFact[];
};
