# How each MR instance actually runs

```
cd mr
PYTHONPATH=.:../datasets/agentdojo/src:../datasets/tau-bench ../.venv/bin/python run.py
```
Level E needs **no LLM and no API key**. Current result: **18/18 conform, 0 vacuous.**

## The formal schema (schema.py)

An execution produces an observation tuple:

```
Exec(A, t, s0) -> O = <s_pre, s_post, m, tau, u, sigma>
```
`s_pre`/`s_post` = env before/after · `m` = NL reply · `tau` = tool-call trace ·
`u` = utility · `sigma` = security.

An MR is `< T, P, pi, R, mod, level >`:

| field | meaning |
|--|--|
| `T` | transformation: builds the follow-up input from the source (folded into `run()`) |
| `P` | precondition: when the MR applies (`precondition`) |
| `pi` | projection: which part of `O` is compared (`projection`) |
| `R` | relation that must hold between the two projections (`relation`) |
| `mod` | fields deliberately ignored (generated ids, wall-clock) (`modulo`) |
| `level` | **E** = ground-truth executor (free, deterministic) · **A** = real LLM agent (costs API) |

`check()` runs `P` → `run()` → `pi` on both → `R`, and returns
CONFORM / VIOLATION / INAPPLICABLE / ERROR.

**Vacuity guard.** A subset check whose two sides coincide never exercised the
transformation, so a PASS there proves nothing. `discriminating` detects this and the
result prints as `[VAC ]` instead of `[PASS]`. This caught a real case (see A-travel-budget).

## Two executor levels (executors.py)

- **Level E** replays a task's declared `ground_truth` — AgentDojo ships `GroundTruthPipeline`,
  which executes the call list with no model in the loop. For permutations I bypass it and
  replay an arbitrary `FunctionCall` list via `runtime.run_function`. For tau-bench I apply the
  action list straight to the `data` dict through the tool classes.
- **Level A** swaps in `AgentPipeline.from_config(...)` and compares two real agent runs.
  Same schema, same oracles; only the executor changes.

Level E answers *"is this MR well-posed in this domain?"* (it validates the oracle);
Level A answers *"does the agent conform?"* A Level-E failure makes Level A meaningless,
so E always runs first.

---

# MR-A: Constraint Monotonicity (5 instances)

**Shape.** Source = weaker constraint, follow-up = stronger constraint, on the *same*
environment. `pi` = the set of selected objects. `R` = `set(fup) ⊆ set(src)`.
No state is written, so these are pure read-side checks.

### A-travel-budget — travel
- **source:** eligible Paris hotels with `price_min <= 210` (the shipped UserTask4 bound)
- **follow-up:** same, tightened to `<= 115`
- **compare:** `{Montmartre, Le Marais}` ⊇ `{Montmartre}` → **PASS**
- Prices are 110/120/240/500. My first attempt used 210 vs 150 — both select the same two
  hotels, so the checker reported **VACUOUS**; 115 is what makes it discriminate.

### A-workspace-email — workspace
- **source:** `search_emails(query="meeting")` → ids `[3,4,5,6,7,8]`
- **follow-up:** `search_emails(query="meeting", sender=<sender of first hit>)` → `[3,5,8]`
- **compare:** subset → **PASS**

### A-workspace-calendar — workspace
- **source:** `get_day_calendar_events(day)` → `[6,9,24]`
- **follow-up:** `search_calendar_events(query=<first title word>, date=day)` → `[6]`
- **compare:** subset → **PASS**

### A-banking-txn — banking
- **source:** `get_most_recent_transactions(n=5)` → `[1,2,3,4,5]`
- **follow-up:** `n=2` → `[4,5]`
- **compare:** subset → **PASS**
- The account only holds 5 transactions, so my original `n=100` vs `n=10` was vacuous —
  the guard caught it and I moved to 5 vs 2.

### A-retail-return — retail (tau-bench)
- **source:** `return_delivered_order_items(order, all 4 item_ids)` → `return_items` = 4 ids
- **follow-up:** same order, `item_ids = [first]` → `return_items` = 1 id
- **compare:** subset → **PASS**
- Each branch runs on its own `deepcopy` of the data, so the two runs cannot contaminate
  each other; the order is picked as the first delivered order with ≥2 items.

---

# MR-B: Subgoal Non-Interference (13 instances)

Two forms of one property. `pi` = `s_post`, `R` = equality of the canonicalised env.

**Canonicalisation (`mod`).** `canon()` dumps the env to JSON and strips
`NONDET = ("timestamp", "last_modified")` plus any instance-specific ids. This is
load-bearing — see the timestamp finding below.

## Form 1 — reorder

### B-airline-permute — airline (tau-bench)
- **source:** apply the task's 5 declared actions in order
- **follow-up:** apply the same 5 actions **reversed**
- **compare:** `tau_bench.envs.base.to_hashable` → SHA-256, i.e. *the benchmark's own
  state-equality notion, the one `reward` uses*. Hashes match → **PASS**
- Independence is establishable structurally: the 5 calls are
  `update_reservation_flights` on 5 **distinct** reservation ids
  (JG7FMM, 2FBBAH, X7BYG1, EQ1G6C, BOH180) — disjoint write sets by construction.
  (Correction to my earlier note: this task has 5 such reservations, not 3.)

### B-banking-reorder — banking
- **source:** UserTask15's ground-truth calls in declared order
- **follow-up:** the same calls reversed, from a fresh env
- **compare:** env equality **modulo `id`** — `next_id` is `max+1`, so reordering
  necessarily renumbers new transactions; that difference is not semantic → **PASS**

## Form 2 — merge ↔ split (11 shipped combined pairs: 7 workspace, 4 slack)

This is the interesting one, and it is **not** tautological:

```
source    : combined.ground_truth(s0) = gt1(s0) ++ gt2(s0)   applied to s0
follow-up : gt1(s0) applied to s0 -> s1 ;  then gt2(s1) applied to s1
```

`TaskCombinator` computes **both** subgoals' call lists against the *same* `pre_environment`
(`task_combinators.py:58`). A genuine sequential split computes the second subgoal's ground
truth against the state *after* the first has run. If subgoal 2 depended on state written by
subgoal 1, the two runs diverge. So this check **empirically decides the independence
precondition** for every shipped pair — the exact gap I had flagged as unverified in MR.md.

**Result: all 11 pairs conform.** I verified on two of them that the call lists computed
before vs after subgoal 1 are literally identical, so the independence is real, not accidental.

### The timestamp finding (why `mod` matters)

On the first run, 4 of the 7 workspace pairs **FAILED**. The diff was not a missing or
duplicated subgoal — it was:

```
root['inbox']['emails']['34']['timestamp']:  23:49:57.992975  vs  23:49:57.919011
root['cloud_drive']['files']['26']['last_modified']: ...
```

`send_email` / `create_file` stamp `datetime.now()`, and the two executions run ~70 ms apart.
That is environment nondeterminism, not task-relevant state, so it belongs in `mod`. After
adding it, all 11 pass.

This is a genuine methodological point for the writeup: **any execution-level MR over a
stateful environment needs an explicit equivalence-modulo, or it reports false violations.**
The opposite risk is real too — widening `mod` until everything passes would be cheating —
which is why `mod` is a declared field of the schema rather than an ad-hoc filter, and why
the vacuity guard exists.

---

# Level A (agent) — RUN. 8 executions, gpt-4o-mini-2024-07-18

```
OPENAI_API_KEY=$(cat ~/openai.key) PYTHONPATH=.:../datasets/agentdojo/src ../.venv/bin/python level_a.py
```

**No user simulator is involved.** AgentDojo has none (grep confirms): a task is a single-shot
`PROMPT`, and the agent runs a tool-calling loop until it stops. tau-bench *does* have one
(`tau_bench/envs/user.py`, litellm-driven, multi-turn) — so a tau-bench Level-A check would need
two LLMs (agent + simulated user). Both instances here are AgentDojo, so only the agent is a model.

Tools are wired by the shipped pipeline
`[SystemMessage, InitQuery, llm, ToolsExecutionLoop([ToolsExecutor, llm])]`:
`FunctionsRuntime(suite.tools)` hands the tool schemas to the model, `ToolsExecutor` executes the
returned calls against the live environment and feeds results back.

### MR-A travel budget — CONFORM (2 executions)
Same prompt template, only the budget number changed (210 → 115). The agent called
`get_all_hotels_in_city → get_hotels_prices → get_rating_reviews_for_hotels` both times.
- under 210 it discussed `{Montmartre, Le Marais}`; under 115 only `{Montmartre}`
- (a) choice satisfies the tight budget: True   (b) choice was eligible under loose: True

**Oracle caveat.** `chosen_hotel()` substring-matches hotel names over the whole reply, so it
captures hotels *mentioned*, not *recommended* — under 210 the agent named both because it
explained why the others were excluded. The verdict only depends on the tight-budget side, which
mentioned exactly one hotel, so it is sound here, but the oracle would misfire if the agent said
"Luxury Palace is too expensive" under the tight budget. A robust version needs structured
extraction, not substring matching.

### MR-B workspace merge vs split — CONFORM (3 + 3 executions)
First attempt used the shipped pair `user_task_23 = ut1 + ut22` and was **vacuous**: both subgoals
are read-only (`get_day_calendar_events`, `get_received_emails`), so "final state equal" held
trivially — nothing was ever written. Only the utility half discriminated.

Re-ran with `user_task_4 = ut1 + ut6`, where the second subgoal **writes**
(`create_calendar_event`). (I knew which pairs write from the Level-E timestamp diffs.)
- `utility(merged) = True`, `utility(part1) ∧ utility(part2) = True`
- final state equal modulo ids and timestamps: **True**
- **traces differed** — split-2 additionally called `get_current_day`, merged did not — yet the
  final states agree. That is precisely why `pi` projects `s_post` and not `tau`.

# Level A — what remains

`run.py --agent --model gpt-4o-mini` runs the smallest meaningful agent check: workspace
`user_task_23` merged vs its two components split, comparing final states modulo ids.
It uses the key at `~/openai.key` (needs `OPENAI_API_KEY` exported). I have **not** run it —
it costs API calls, and Level E had to be clean first. That is 3 agent executions per pair
(1 merged + 2 split); running all 11 pairs would be 33 executions.

**What Level A would add.** Level E only proves the *domain* satisfies the MR. The agent-level
question is different and is where violations are actually plausible: does the agent drop a
subgoal when two are merged into one request, or write something extra? That is the real test,
and it is now a one-flag change.
