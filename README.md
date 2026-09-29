# Relay — Distributed Policy Propagation

An offline-first research demo with two presentation modes. App 1 is a single deterministic replay of a distributed lifecycle-propagation failure. App 2 shows how message-carried knowledge labels interact with each principal's tracked disclosure state through a synchronized side-by-side comparison.

## Applications

- **App 1 — Underground Coordination:** required safety knowledge must propagate through distributed principals. It is presented as one chronological episode without an invented label-based counterfactual.
- **App 2 — Knowledge-Combination Budget Audit:** individually permissible disclosure atoms must sometimes remain distributed. A locally acceptable message is withheld when its prospective release would complete an explicit forbidden set. It is presented as the side-by-side unlabeled/labeled comparison.

App 1 motivates the distributed-state problem. App 2 implements Local Disclosure-Combination Control: tracked disclosure state + incoming knowledge labels + explicit forbidden sets + policy exemptions → allow or deny. Its paired timeline aligns the same audit event in both branches, then shows where local state and the final disclosure outcome diverge.

For a self-contained handoff of App 2—including its scenario, policies, enforcement semantics, knowledge-tag mechanism, comparison design, implementation map, and current limitations—start with [`APP2_SPEC.md`](./APP2_SPEC.md). A new agent should not need the other App 2 notes to understand the current application.

## Run locally

```bash
npm install
npm run dev
```

Use the header tabs to switch applications. In App 1, **Next step** advances the single replay. In App 2, **Next beat** advances both branches together. Click a principal or colored message route to inspect the state and payload for the active episode or branch.

## Architecture

- `episodes/index.ts` — source episode registry; App 1 remains available here for later standalone presentation
- `episodes/heat-revocation/episode.ts` — typed, machine-readable timeline and complete rendering source of truth
- `episodes/heat-revocation/narrative.md` — separate researcher-facing narrative (never parsed by the app)
- `episodes/budget-compartment/episode.ts` — App 2's declarative Q1–Q2 audit episode, disclosure state, denial, escalation, and attestation
- `episodes/budget-compartment/policy.md` — the concrete ten-policy App 2 specification
- `episodes/budget-compartment/model.md` — standalone English specification of the Local Disclosure-Combination Control model
- `episodes/budget-compartment/narrative.md` — concise App 2 application description
- `episodes/comparisons.ts` — App 2's aligned unlabeled/labeled counterfactual beats
- `src/types/episode.ts` — reusable episode schema
- `src/simulator/selectors.ts` — generic, read-only frame selectors
- `src/components/` — episode-agnostic graph, simplified fact/inference inspector, message inspector, and on-demand policy reference
- `src/policy/status.ts` — policy presentation boundary, ready for a later rule-engine adapter
- `src/policy/disclosure.ts` — recipient-local forbidden-set evaluator with fail-closed unknown-domain handling

Every frame includes authoritative resources, every principal's established/received/derived knowledge, messages and lifecycle states, policy evaluation, attempted effects, and annotations. Facts and messages can carry issuer, source, scope, version, validity, audience, forwarding path, provenance, supersession, and flow restrictions. Navigation selects a frame directly; it never mutates or reconstructs prior world state.

## Add another episode

Create a folder under `episodes/`, export an `Episode` object matching `src/types/episode.ts`, and a separate `narrative.md`. Import and register it in `episodes/index.ts`. The header switcher enables it automatically; no visualization component changes are required.
