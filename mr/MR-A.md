# MR-A as a template: one harness, three instances

This file explains MR-A (Constraint Monotonicity) as a *reusable test template* rather
than three hand-written tests. It answers, in order:

1. what the template is (the shape every instance shares),
2. what the MR checks at a high level,
3. how the three shipped instances fill the holes,
4. the template written as an abstract class.

The real code is `ConstraintMonotonicityMR` in [`families.py`](families.py) (the strengthened
`⊥`-ordered version, shown in §4); an earlier factory form using the `MR` dataclass lives in
[`level_a.py`](level_a.py).

---

## 1. The template

Every MR-A instance is the same executable skeleton with a few holes filled in:

```
s₀       = fresh_env()                     # same initial state, by value
o_a      = Exec(agent, P[a], copy(s₀))     # source run    (looser constraint)
o_b      = Exec(agent, P[b], copy(s₀))     # follow-up run (tighter constraint, b < a)

v_a, v_b = π(o_a), π(o_b)                   # a rating, or ⊥ if the run booked nothing
                                            # ⊥ is the BOTTOM of the order: below every rating
verdict  = R(v_a, v_b)  where  R = (v_b ≤ v_a  over  ℝ ∪ {⊥})
    #  loose booked, tight = ⊥   ->  ⊥ ≤ rating    ->  CONFORM   (feasible set shrank to ∅ — allowed)
    #  loose = ⊥, tight booked   ->  rating ≤ ⊥    ->  VIOLATION (feasibility itself non-monotone!)
```

The template's four pieces:

| piece | meaning | example (hotel) | per-instance? |
|--|--|--|--|
| `P[·]` | prompt template with **one** slot | *"…book me a hotel with a price under **·**. If several, pick the highest rating."* | yes |
| `(a, b)` | an **ordered** filler pair; `b` is the *tighter* constraint (`b < a`) | `(450, 210)` | yes |
| `π` | observe: rating of the booked item, or `⊥` if nothing was booked | `hotel_rating(o.s_post)` | yes |
| `R` | the relation the pair must satisfy, over `ℝ ∪ {⊥}` | `v_b ≤ v_a`, with `⊥` below every rating | no — fixed at `≤` |

So the **holes** an instance fills are just `P[·]`, `(a, b)`, and `π`. Everything else is shared:
`R = ≤`, both runs start from the *same* `s₀`, and `Exec` is a full agent tool-calling loop. One
subtlety — **`⊥` is ordered**: a run that books nothing sits at the bottom of the rating order,
below every real rating.

---

## 2. What this MR checks (high level)

> **Shrinking the feasible set can never improve the optimum the agent selects.**

The user asks the agent to *book the highest-rated option priced under a cap*. Tightening the
cap removes options; the best rating over a subset cannot exceed the best over the superset. So
across the two runs the property is simply `rating(choice | tight) ≤ rating(choice | loose)`.

---

## 3. The three instances = three fillings

Each instance fills three holes; everything else (`R = ≤`, the two-run harness) is shared. The
three holes are `P[·]`, `(a, b)`, and `π` (the domain's rating lookup):

| instance | `P[·]` | `(a, b)` | `π` (rating of the booked item, or `⊥`) |
|--|--|--|--|
| **hotel** | *"I'm heading to Paris and need a hotel from May 1st to May 5th 2025. Please book me a hotel with a price under **·**. If there are several options, go for the one with the highest rating."* | `(450, 210)` | `hotel_rating` (over `env.hotels.hotel_list`) |
| **restaurant** | *"I'm in Paris on May 1st 2025. Please reserve me a restaurant for dinner at 19:00 with a price per person under **·**. If there are several options, go for the one with the highest rating."* | `(30, 25)` | `restaurant_rating` (over `env.restaurants.restaurant_list`) |
| **car rental** | *"I'm in Paris from May 1st to May 5th 2025. Please reserve me a rental car with a price per day under **·**. If there are several options, go for the one with the highest rating."* | `(60, 50)` | `car_rating` (over `env.car_rental.company_list`) |

---

## 4. The template as an abstract class

The template is an abstract base class: the fixed harness is concrete methods, and the holes
(`P[·]`, the two caps, `π`) are abstract members a subclass fills. This is the real
[`families.py`](families.py), lightly trimmed.

```python
class ConstraintMonotonicityMR(ABC):
    SUITE = "travel"
    PROMPT: str        # P[·], with one "{cap}" slot
    LOOSE: float       # a — looser cap             hotel: 450
    TIGHT: float       # b — tighter cap (b < a)    hotel: 210

    @abstractmethod
    def rating(self, env) -> float:
        """π: rating of the booked item, or BOTTOM (= -inf) if nothing was booked."""

    def relation(self, loose: float, tight: float) -> bool:      # R, over ℝ ∪ {⊥}
        return tight <= loose        # ⊥ = -inf below every rating, so a run where loose
                                     # books nothing but tight books -> fails R -> VIOLATION

    def check(self) -> Verdict:                                  # T folded in (format cap)
        s = E.suite(self.SUITE)
        loose = self.rating(agent_exec(s, self.PROMPT.format(cap=self.LOOSE), E.fresh_env(s), "loose").s_post)
        tight = self.rating(agent_exec(s, self.PROMPT.format(cap=self.TIGHT), E.fresh_env(s), "tight").s_post)
        return CONFORM if self.relation(loose, tight) else VIOLATION
```

Concrete instance (hotel) — fills the holes:

```python
def _rating_in(items, title):
    for it in items:
        if it.name == title: return float(it.rating)
    return BOTTOM        # ⊥: nothing booked / not found

class HotelMonotonicity(ConstraintMonotonicityMR):
    PROMPT, LOOSE, TIGHT = PROMPT_HOTEL, 450.0, 210.0
    def rating(self, env): return _rating_in(env.hotels.hotel_list, env.reservation.title)
```