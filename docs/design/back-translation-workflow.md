# Independent back-translation workflow

Back-translation explains the installed added enforcement. Application logic is
evidence only for necessary input sources, actual effect boundaries, delegated
checks and bypasses. It does not reconstruct the application's business workflow.
The source policy, forward plans and tests stay outside the reverse model input.

## Host stages

| Stage | Artifact | Checks |
| --- | --- | --- |
| Freeze implementation inputs | `input-manifest.json` | Pin actual rules, trusted input meanings/configuration and implementation evidence. Repository reading excludes original policy, forward plans and tests. |
| Reconstruct enforcement | `checks.json` | One independently reviewable requirement per check. Retain inputs and lifecycle, conditions, alternative branches, consuming gate, delegated checks, gaps and exact citations. Cover every rule ID. |
| Describe frozen checks | `backtranslation.json` | A separate model call receives accepted chains, without the application source bundle. Preserve check IDs; the host attaches accepted rule references, input summaries and evidence. |
| Validate and retain | `workflow.json` | Check structure, exact citations, complete rule references and one description per frozen check. Retain failures and bounded repairs. Publish a repository reading pointer only on success. |

Both model stages use the injected `generate(stage, prompt)` boundary. The generic
CLI uses the compatible transport; repository reading uses separate isolated,
ephemeral coding sessions with read-only input files. Presentation cannot edit
the host's accepted chains. These reading sessions do not execute the application.
An explicit new run retains earlier evidence. A failed run does not replace a
successful repository reading pointer.

Reconstruction must distinguish allowance, explicit refusal, entry/validation
errors and permission to let an original tool report an error. It includes
global invariants and their interaction with positive branches. A recorded
post-success result supports a later decision, not its own producing operation.
Missing producers, reported identity, restart limitations and unmediated effects
remain attached to the affected check.

The model interprets those relationships. Structural checks and exact quotations
do not prove their correctness, branch completeness, semantic equivalence,
exhaustive mediation or consistency between prose and code. Illustrative examples
are model descriptions with supporting rule IDs, not executed test results.

## Student presentation

The review keeps source sentences on the left and relevant independent checks on
the right. Each check has a required short summary with decisive conditions and
material dependencies or gaps. “How this is checked” reveals concise details in
condition-first order, followed by necessary source/timing context. Each check
has at most three detail lines, each at most 360 characters. Internal method names
and event/field plumbing stay in reconstruction evidence. The UI also
accepts older descriptions with A/B/C annotations, without showing fixed sections.

“Examples” appears only when a check has an illustrative scenario. Examples
describe the outcome of that check, not guaranteed authorization or business
success. They stay folded by default. No examples are required for simple checks.
Code evidence remains in the data artifacts.

After the independent reading freezes, the viewer's separate alignment pass may
read source policy and map sentences to relevant check IDs. It cannot rewrite
the reading or assign a correctness judgment. Human review remains necessary.

## UI copy

The added control is “Examples”. Its label is needed to open optional illustrations;
it appears only on checks with examples, and its content is disclosed on demand.
The existing “How this is checked” control remains. Fixed “Recorded information”,
“Decision rules” and “Before execution” captions are removed to avoid repeating
the same condition across three mandatory-looking sections.
