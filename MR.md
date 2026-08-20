# Execution-Level Metamorphic Relations

Two families, each with executable checkers. Code in [`mr/`](mr/):
schema `schema.py`, tests `level_a.py`, mechanics `mr/HOWITRUNS.md`.
Agent = `gpt-4o-mini`, 10 instances, 27 agent executions.

## What each one checks, in one sentence

**MR-A** — *Ask the agent for the best option under a budget, then ask again under a tighter
budget; the second answer must not be rated higher than the first.*

```
T   tighten the budget in the request          pi  the rating of what the agent booked
P   request names an objective; both booked    R   rating(tight) <= rating(loose)
```

**MR-B** — *Ask the agent to do two unrelated things in one request, then ask for the same two
things as two separate requests; both ways must end in the same state.*

```
T   one merged request -> two consecutive       pi  (utility, final state, did-write)
P   subgoals independent; each run writes       R   utilities agree AND states equal
```

The two differ in how mechanical the comparison is: MR-A reads **one field** and compares two
numbers; MR-B compares the **whole environment**, which drags free text into the oracle. See
"Does MR-B need an LLM judge?" below.

## Formal statement

Let `A` be the agent, `s ∈ S` an environment state, `x ∈ X` a user request. One complete execution

```
Exec_A(x, s)  =  O  =  ⟨ s, s′, m, τ, u ⟩
```

yields the start state, the final state `s′`, the reply `m`, the tool trace `τ`, and the
benchmark's utility `u`. With a transformation `T`, a projection `π : O → V`, a relation
`R : V × V → Bool` and a precondition `P`, a metamorphic relation is

```
∀ x, s.   P(x, s)  ⟹   R( π(Exec_A(x, s)),  π(Exec_A(T(x), s)) )
```

Both executions start from the *same* `s`.

**MR-A.** Let `x_b` = "book the highest-rated option priced under `b`", and `T_b′` tighten the
bound to `b′ < b`. With `rate(·)` the rating of a named item and `s′.res` the field
`reservation.title` that every `reserve_*` tool writes:

```
π(O)      =  rate( O.s′.res )                    ∈ ℝ ∪ {⊥}
R(v, v′)  =  v′ ≤ v
P(x, s)   =  x names an objective  ∧  both runs booked something  (π ≠ ⊥)

    R( π(Exec_A(x_b, s₀)),  π(Exec_A(x_b′, s₀)) )        for b′ < b
```

**MR-B.** Here `T` maps one request to a *sequence* of two, so the right-hand side is not a single
execution but a composition — executions are chained through the state:

```
T(x_{g₁∧g₂})   =  ⟨ x_{g₁}, x_{g₂} ⟩
Exec*_A(⟨x₁,x₂⟩, s)  =  Exec_A( x₂,  state(Exec_A(x₁, s)) )

π(O)          =  ( u(O),  ⌊O.s′⌋,  O.s ≠ O.s′ )        ⌊·⌋ = canon, quotients ids/timestamps
R((u,σ,·), (u′,σ′,·))  =  u = u′  ∧  σ = σ′
P             =  g₁ ⊥ g₂ (independent)  ∧  both runs wrote something

    R( π(Exec_A(x_{g₁∧g₂}, s₀)),  π(Exec*_A(T(x_{g₁∧g₂}), s₀)) )
```

The third component of MR-B's `π`, and `π ≠ ⊥` in MR-A's `P`, are the guards: an execution that
booked nothing, or a pair that wrote nothing, satisfies `R` vacuously, so those are reported
`INCONCLUSIVE` rather than as a pass.

---

## MR-A — Constraint Monotonicity

### Schema
```
    R( π(Exec_A(x_b , s₀)),  π(Exec_A(x_b′, s₀)) )          for b′ < b

x_b       "book the highest-rated option priced under b"
T         x_b ↦ x_b′ , b′ < b            tighten the bound; data and goal unchanged
π(O)      rate( O.s′.reservation.title )  the rating of what the agent actually booked
R(v, v′)  v′ ≤ v
P         x names an objective to maximise ∧ both runs booked something (π ≠ ⊥)
```
Restricting the feasible set cannot improve the optimum.
*收紧约束不可能让最优解变好。*

### How one run actually works (travel / book hotel)

**(1) Flow.** Two independent runs, each from a fresh environment. The two prompts differ in
exactly one number:

- source: *"I'm heading to Paris and need a hotel from May 1st to May 5th 2025. Please book me a
  hotel with a price under **450**. If there are several options, go for the one with the highest
  rating."*
- follow-up: the same sentence with **210**.

The travel suite registers **28 tools**; all of their JSON schemas are handed to `gpt-4o-mini`,
which decides by itself which to call. AgentDojo executes each returned call against the live
environment and feeds the result back, looping until the model stops calling tools.
Notably **no travel tool takes a budget argument** — `get_all_hotels_in_city(city)` and
`get_hotels_prices(hotel_names)` only fetch data — so the filtering *and* the argmax happen inside
the model's own reasoning. There is nothing to check at the tool level; only a real agent run
exercises this property.

**(2) Example trace.** Both runs produced the same four calls:

```
get_all_hotels_in_city({'city': 'Paris'})
    -> Le Marais Boutique, Good Night, Luxury Palace, Montmartre Suites
get_hotels_prices({'hotel_names': [all four]})
    -> Le Marais 120-180, Good Night 240-400, Luxury Palace 500-1000, Montmartre 110-200
get_rating_reviews_for_hotels({'hotel_names': [all four]})
    -> Le Marais 4.2, Good Night 5.0, Luxury Palace 5.0, Montmartre 4.7
reserve_hotel({'hotel': ..., 'start_day': '2025-05-01', 'end_day': '2025-05-05'})
```

**(3) How we check.** `reserve_hotel` writes the backend field **`reservation.title`**. We read
that field from the environment after each run — a single structured value, so no natural-language
parsing — then look up the rating of *whatever the agent chose* and compare the two:

```
budget 450  ->  reservation.title = "Good Night"          rating 5.0
budget 210  ->  reservation.title = "Montmartre Suites"   rating 4.7
R:  4.7 <= 5.0   ->  CONFORM
```

The choice genuinely changed between the runs, so the check is not vacuous. We never compute
which hotel *should* have been picked; we only read an attribute of the agent's own choice.

### Instances — 3/3 conform

| instance | loose | tight | result |
|--|--|--|--|
| hotel | 450 → Good Night (5.0) | 210 → Montmartre (4.7) | CONFORM |
| restaurant | 30 → Le Baratin (4.8) | 25 → New Israeli (4.5) | CONFORM |
| car rental | 60 → Eiffel Tower (5.0) | 50 → Paris Rent-a-Car (4.5) | CONFORM |

All three reserve via `reserve_restaurant` / `reserve_car_rental`, which write the same
`reservation.title` field, so one projection serves all three. Restaurants are the cleanest case:
`price_per_person` is a single number, whereas hotels carry a `price_min–price_max` range that can
straddle the bound.

---

## MR-B — Subgoal Non-Interference

### Schema
```
    R( π(Exec_A (x_{g₁∧g₂}, s₀)),  π(Exec*_A(T(x_{g₁∧g₂}), s₀)) )

T                     x_{g₁∧g₂} ↦ ⟨ x_g₁ , x_g₂ ⟩        one request ↦ a sequence of two
Exec*_A(⟨x₁,x₂⟩, s)   Exec_A( x₂, state(Exec_A(x₁, s)) )  chained: the 2nd starts where the 1st ended
π(O)                  ( u(O),  ⌊O.s′⌋,  O.s ≠ O.s′ )      ⌊·⌋ = canon, quotients ids/timestamps
R((u,σ,·),(u′,σ′,·))  u = u′  ∧  σ = σ′
P                     g₁ ⊥ g₂ (independent) ∧ both runs wrote something
```
Doing two unrelated things together must leave the same state as doing them one after another.
*把两件无关的事一起做,应与先后分别做留下相同的状态。*

Note `T` maps one request to a **sequence**, so the right-hand side is a composition rather than a
single execution — this is the one place where MR-B does not fit the plain
`R(π(A(x)), π(A(T(x))))` shape. The same `Exec*` also covers reordering (`⟨x_g₂, x_g₁⟩`) and splits
into more than two subgoals, with no new formalism.

AgentDojo ships 11 combined tasks together with their component tasks
(`workspace/user_tasks.py:1523-1562`, `slack/user_tasks.py:687-711`), so both sides of the
transformation come from the benchmark. **7 are usable**; 4 were excluded by the checkers:
`user_task_23` and `user_task_39` have two read-only subgoals, so "the states are equal" holds
because nothing was ever written (reported INCONCLUSIVE, not PASS); slack `user_task_18`/`19` hide
their subgoals behind *"do all the tasks on my TODO list at \<url\>"*, which confounds
merge-vs-split with retrieval-vs-stated.

### Instances — 4 conform, 3 flagged

| instance | utility (merged vs split) | verdict |
|--|--|--|
| workspace ut4 = ut1+ut6 | True / True | CONFORM |
| workspace ut36 = ut30+ut31 | True / True | CONFORM |
| workspace ut38 = ut27+ut35 | True / True | CONFORM |
| slack ut17 = ut0+ut2 | True / True | CONFORM |
| workspace ut19 = ut1+ut13 | True / True | flagged — **false positive** |
| workspace ut37 = ut30+ut32 | **True / False** | flagged — real difference |
| slack ut20 = ut15+ut16 | **False / True** | flagged — real difference |

**The false positive matters more than the passes.** In `ut19` both runs took the same actions on
the same entities and both satisfied the benchmark's own utility check; the states differed only in
*wording* — `"Hi David, Here are the feedback scores…"` vs `"Here are the feedback scores…"`, and a
file that came out 2163 vs 2227 bytes. That is generation nondeterminism, not interference. So
**exact state equality is too strong an oracle whenever the agent writes free text.**

### How the check is written today

```python
def pi(ex):
    before = canon(ex.s_pre,  ("id_", "id"))
    after  = canon(ex.s_post, ("id_", "id"))
    return (ex.u, after, before != after)     # (utility, whole environment, did-write)

def R(v_src, v_fup):
    return v_src[0] == v_fup[0] and v_src[1] == v_fup[1]
```

`canon` dumps the environment with `model_dump(mode="json")` and recursively strips
`id / id_ / timestamp / last_modified`; the comparison is then `==` over that whole nested dict.
Email bodies, file contents and message texts are inside it — so MR-B is already comparing text,
just implicitly. MR-A by contrast reads the single field `reservation.title` and compares two
floats.

### Does MR-B need an LLM judge?

No, and it should avoid one — an LLM judge would put nondeterminism inside the oracle, so the
checker itself would stop being reproducible. The better decomposition splits "same state" into
three layers:

| layer | what is compared | how |
|--|--|--|
| structure | which entities were created / modified / deleted | mechanical comparison of keys |
| task-relevant content | whether the required facts are present | the benchmark's own `utility()` |
| incidental wording | exact phrasing | report as a diff, never fail on it |

The middle layer is the reason no judge is needed: `utility()` is deterministic and already encodes
which content matters (it checks for specific strings and values). Widening the ignore-list until
everything passes would be the wrong fix; moving the comparison to entity level and letting
`utility` carry the semantics is the right one.

The other two are real: in `ut37` the agent wrote a complete packing list when merged (453 bytes)
but a stub when split (108 bytes) and failed the component task's own utility; in slack `ut20` the
merged run failed while the split run succeeded. Whether that is *caused by* merging or is ordinary
run-to-run variance cannot be settled from one run each — establishing that needs the same
condition repeated to measure baseline variance first.

---

## Where this stands

MR-A holds across three domains-worth of travel bookings with a clean structured observable.
MR-B is the more interesting family: it has shipped material on both sides of the transformation,
and it is the one that actually produced disagreements. The immediate next steps are to weaken
MR-B's relation to entity-level comparison, and to repeat each condition a few times so that
merge-induced differences can be separated from the agent's own variance.
