"""Formal schema for execution-level metamorphic relations (MRs).

An *execution* of an agent on a task yields an observation tuple; an *MR* constrains
a pair of executions related by an input transformation.

    Exec(A, t, s0)  ->  O = <s_pre, s_post, m, tau, u, sigma>

        s_pre   pre-environment (state before the agent acts)
        s_post  post-environment (state after)
        m       natural-language reply to the user
        tau     tool-call trace (ordered sequence of FunctionCall)
        u       task utility        (benchmark-supplied oracle, may be None)
        sigma   security predicate  (benchmark-supplied oracle, may be None)

An MR is the 6-tuple

    MR = < T, P, pi, R, mod, level >

        T      transformation  (t, s0) -> (t', s0')      the follow-up input
        P      precondition    (t, s0) -> bool           when the MR is applicable
        pi     projection      O -> V                    the observable actually compared
        R      relation        (V_src, V_fup) -> bool    what must hold between them
        mod    equivalence modulo: fields deliberately ignored when comparing
               (generated identifiers, record insertion order, timestamps)
        level  E = environment/tool semantics (executor = ground truth, deterministic, free)
               A = agent conformance          (executor = LLM agent, stochastic, costs API)

Level E asks "is this MR well-posed in this domain?" -- it validates the oracle.
Level A asks "does the agent conform?" -- it is the actual test.
A Level-E failure means the MR is unsound for that domain and Level A is meaningless
there, so E is always run first.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Level(StrEnum):
    ENV = "E"  # ground-truth executor, deterministic, no LLM
    AGENT = "A"  # real agent, stochastic, costs API calls


class Verdict(StrEnum):
    CONFORM = "conform"
    VIOLATION = "violation"
    INAPPLICABLE = "inapplicable"  # precondition P false
    INCONCLUSIVE = "inconclusive"  # an execution produced no judgeable observable
    ERROR = "error"


@dataclass
class Execution:
    """Observation tuple O of a single complete execution."""

    s_pre: Any = None
    s_post: Any = None
    m: str | None = None
    tau: Sequence[Any] = field(default_factory=list)
    u: bool | None = None
    sigma: bool | None = None
    label: str = ""

    def tool_names(self) -> list[str]:
        out = []
        for c in self.tau:
            out.append(getattr(c, "function", None) or getattr(c, "name", str(c)))
        return out


@dataclass
class MRResult:
    mr_id: str
    family: str
    domain: str
    level: Level
    verdict: Verdict
    detail: str = ""
    src_view: Any = None
    fup_view: Any = None
    vacuous: bool = False  # transformation did not change the observable -> PASS is uninformative

    def line(self) -> str:
        mark = {
            Verdict.CONFORM: "PASS",
            Verdict.VIOLATION: "FAIL",
            Verdict.INAPPLICABLE: "n/a ",
            Verdict.INCONCLUSIVE: "INC ",
            Verdict.ERROR: "ERR ",
        }[self.verdict]
        if self.vacuous and self.verdict is Verdict.CONFORM:
            mark = "VAC "
        return f"[{mark}] {self.level}  {self.mr_id:<26} {self.family:<16} {self.domain:<10} {self.detail}"


@dataclass
class MR:
    """A metamorphic relation, instantiated for one concrete domain scenario."""

    id: str
    family: str  # "monotonicity" | "non-interference"
    domain: str
    level: Level
    statement: str  # domain-level semantic property, in words
    evidence: str  # benchmark file/task backing this instance

    # T is folded into `run`, since building the follow-up input is domain specific.
    precondition: Callable[[], bool] | None = None
    projection: Callable[[Execution], Any] | None = None
    relation: Callable[[Any, Any], bool] | None = None
    modulo: tuple[str, ...] = ()
    # Did the transformation actually move the observable? If not, a PASS proves nothing.
    discriminating: Callable[[Any, Any], bool] | None = None
    # Is a projected observable judgeable at all? (e.g. the agent booked nothing.)
    # Without this, an empty/None observable can satisfy R vacuously and be scored a PASS.
    well_formed: Callable[[Any], bool] | None = None

    # run() must produce the (source, follow-up) execution pair.
    run: Callable[[], tuple[Execution, Execution]] | None = None

    def check(self) -> MRResult:
        try:
            if self.precondition is not None and not self.precondition():
                return MRResult(self.id, self.family, self.domain, self.level,
                                Verdict.INAPPLICABLE, "precondition P false")
            assert self.run is not None and self.projection is not None and self.relation is not None
            src, fup = self.run()
            v_src, v_fup = self.projection(src), self.projection(fup)
            if self.well_formed is not None and not (
                self.well_formed(v_src) and self.well_formed(v_fup)
            ):
                bad = [n for n, v in (("src", v_src), ("fup", v_fup)) if not self.well_formed(v)]
                return MRResult(self.id, self.family, self.domain, self.level,
                                Verdict.INCONCLUSIVE,
                                f"no judgeable observable on: {', '.join(bad)} "
                                "(execution produced no result / wrote nothing)")
            ok = self.relation(v_src, v_fup)
            # A subset-style check whose two sides coincide did not exercise the
            # transformation at all; a PASS there is uninformative, not evidence.
            vac = self.discriminating is not None and not self.discriminating(v_src, v_fup)
            detail = self._describe(v_src, v_fup, ok)
            if vac:
                detail += "  [VACUOUS: transformation changed nothing]"
            return MRResult(
                self.id, self.family, self.domain, self.level,
                Verdict.CONFORM if ok else Verdict.VIOLATION, detail, v_src, v_fup, vac,
            )
        except Exception as e:  # noqa: BLE001 - a checker crash must not abort the suite
            return MRResult(self.id, self.family, self.domain, self.level,
                            Verdict.ERROR, f"{type(e).__name__}: {e}")

    def _describe(self, a: Any, b: Any, ok: bool) -> str:
        def short(x: Any) -> str:
            if isinstance(x, (set, frozenset)):
                return f"|{len(x)}|"
            s = str(x)
            return s if len(s) <= 60 else s[:57] + "..."

        rel = "OK" if ok else "BROKEN"
        mod = f" (mod {','.join(self.modulo)})" if self.modulo else ""
        return f"src={short(a)} fup={short(b)} -> {rel}{mod}"
