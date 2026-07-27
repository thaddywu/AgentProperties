#!/usr/bin/env python3
"""
LEVEL A -- agent-output metamorphic tests.

We compare two COMPLETE AGENT EXECUTIONS related by an input transformation:

        Exec(agent, input)   vs   Exec(agent, T(input))

Each test below is a literal instance of the `MR` schema in schema.py, so the five
formal components are visible as named fields:

        T    the input transformation            (what differs between the two runs)
        P    precondition                        (when the MR applies)
        pi   projection                          (what part of the execution we look at)
        R    relation                            (what must hold between the two)
        mod  equivalence-modulo                  (what we deliberately ignore)

Environment notes:
  * AgentDojo has NO user simulator -- a task is a single-shot PROMPT and the agent runs
    a tool-calling loop until it stops. The only model in the loop is the agent.
    (tau-bench DOES have an LLM-simulated user, so a tau-bench test would need 2 models.)
  * Tools are wired by AgentDojo's own pipeline:
        [SystemMessage, InitQuery, llm, ToolsExecutionLoop([ToolsExecutor, llm])]
    FunctionsRuntime(suite.tools) gives the model the tool schemas; ToolsExecutor runs
    the returned calls against the live environment and feeds results back.

Run:  OPENAI_API_KEY=$(cat ~/openai.key) python level_a.py
"""
from __future__ import annotations

import collections
import os
import sys

import executors as E
from agentdojo.agent_pipeline.agent_pipeline import AgentPipeline, PipelineConfig
from agentdojo.functions_runtime import FunctionsRuntime
from agentdojo.task_suite.task_suite import model_output_from_messages
from executors import canon
from schema import Execution, Level, MR, Verdict

MODEL = os.environ.get("MR_MODEL", "gpt-4o-mini-2024-07-18")


# ===========================================================================
# The executor: one complete agent execution
# ===========================================================================

def agent_exec(suite, prompt: str, env, label: str) -> Execution:
    """Run the agent to completion on `prompt` against `env`; return the observation tuple."""
    pipeline = AgentPipeline.from_config(
        PipelineConfig(llm=MODEL, model_id=None, defense=None,
                       system_message_name=None, system_message=None)
    )
    runtime = FunctionsRuntime(suite.tools)
    pre = env.model_copy(deep=True)
    _, _, post, messages, _ = pipeline.query(prompt, runtime, env)

    out = model_output_from_messages(messages)
    text = "" if out is None else (
        out if isinstance(out, str)
        else "\n".join(b.get("content", "") if isinstance(b, dict) else str(b) for b in out)
    )
    trace = [c for m in messages
             if m.get("role") == "assistant" and m.get("tool_calls")
             for c in m["tool_calls"]]

    print(f"    [{label}] tools = {[c.function for c in trace]}")
    print(f"    [{label}] says  : {text[:150].strip()}...")
    return Execution(s_pre=pre, s_post=post, m=text, tau=trace, label=label)


# ===========================================================================
# TEST 1 -- MR-A: Constraint Monotonicity   (travel, hotel budget)
# ===========================================================================
#
# Domain property:
#   "When booking a hotel under a budget, tightening the budget only reduces the
#    set of hotels that remain eligible."
#
# Why this one needs a real agent: travel ships NO tool with a filter parameter
# (get_all_hotels_in_city(city), get_hotels_prices(hotel_names) -- no budget arg).
# The budget constraint is applied entirely inside the agent's reasoning, so there
# is no tool-level shadow of this MR to check. Level A is the only way to test it.

# The task asks the agent to BOOK, not to describe. So the observable is the resulting
# reservation in the environment (every reserve_* tool writes reservation.title), which is
# a single structured value -- no natural-language extraction, no ambiguity.
#
# Selection rule in the prompt: argmax(rating) over {item : price(item) <= budget}.
# Tightening the budget shrinks that feasible set, and a maximum over a subset cannot
# exceed the maximum over the superset. That is exactly what R checks.

PROMPT_HOTEL = ("I'm heading to Paris and need a hotel from May 1st to May 5th 2025. "
                "Please book me a hotel with a price under {budget}. "
                "If there are several options, go for the one with the highest rating.")
PROMPT_RESTAURANT = ("I'm in Paris on May 1st 2025. Please reserve me a restaurant for dinner "
                     "at 19:00 with a price per person under {budget}. "
                     "If there are several options, go for the one with the highest rating.")
PROMPT_CAR = ("I'm in Paris from May 1st to May 5th 2025. Please reserve me a rental car with a "
              "price per day under {budget}. "
              "If there are several options, go for the one with the highest rating.")

# (kind, prompt, loose, tight, how to list candidates as (name, rating))
# Budgets are chosen so the agent's best choice actually changes between the two runs.
MR_A_SPECS = [
    ("hotel", PROMPT_HOTEL, 450.0, 210.0,
     lambda env: [(h.name, h.rating) for h in env.hotels.hotel_list]),
    ("restaurant", PROMPT_RESTAURANT, 30.0, 25.0,
     lambda env: [(r.name, r.rating) for r in env.restaurants.restaurant_list]),
    ("car rental", PROMPT_CAR, 60.0, 50.0,
     lambda env: [(c.name, c.rating) for c in env.car_rental.company_list]),
]


def mr_a(kind="hotel", prompt=PROMPT_HOTEL, loose=450.0, tight=210.0, candidates=None) -> MR:
    """Constraint monotonicity: tightening the budget cannot improve the chosen rating."""
    suite = E.suite("travel")
    candidates = candidates or MR_A_SPECS[0][4]

    def pi(ex: Execution):
        """pi : (what the agent reserved, its rating), read from the environment.

        Reads an attribute of the agent's OWN choice; it never computes what the
        correct choice would have been.
        """
        booked = ex.s_post.reservation.title
        if not booked:
            return None
        for name, rating in candidates(ex.s_post):
            if name == booked:
                return (name, float(rating))
        return None

    def T_and_run():
        """T : tighten the budget. Everything else identical."""
        src = agent_exec(suite, prompt.format(budget=loose), E.fresh_env(suite), f"{kind} <={loose}")
        fup = agent_exec(suite, prompt.format(budget=tight), E.fresh_env(suite), f"{kind} <={tight}")
        return src, fup

    return MR(
        id=f"A-travel-{kind.replace(' ', '')}", family="monotonicity", domain="travel",
        level=Level.AGENT,
        statement=("Tightening the budget cannot improve the rating of what the agent books: "
                   "rating(choice|tight) <= rating(choice|loose)."),
        evidence="travel/user_tasks.py UserTask4 :372-374 ships both a bound ('under 210') and "
                 "the objective ('go for the highest rating'); no travel tool filters by price, "
                 "so both the filtering and the argmax are done by the agent",
        run=T_and_run, projection=pi,
        relation=lambda a, b: b[1] <= a[1],
        well_formed=lambda v: v is not None,
        discriminating=lambda a, b: a != b,
    )


def all_mr_a() -> list[MR]:
    return [mr_a(k, p, lo, ti, c) for k, p, lo, ti, c in MR_A_SPECS]


# ===========================================================================
# TEST 2 -- MR-B: Subgoal Non-Interference   (workspace, merge vs split)
# ===========================================================================
#
# Domain property:
#   "When a user asks for two unrelated workspace actions in a single request,
#    carrying them out together should leave the mailbox/calendar/drive in the same
#    task-relevant state as carrying them out as two consecutive requests."
#
# T : one merged request  ->  two consecutive requests in the SAME environment.
#
# Instance choice matters: user_task_23 (= ut1 + ut22) is VACUOUS here because both
# subgoals are read-only -- "state unchanged" holds trivially. We use
# user_task_4 (= ut1 + ut6), whose second subgoal WRITES (create_calendar_event).

def mr_b(domain="workspace", combined="user_task_4",
         p1="user_task_1", p2="user_task_6") -> MR:
    suite = E.suite(domain)
    ct, t1, t2 = suite.user_tasks[combined], suite.user_tasks[p1], suite.user_tasks[p2]

    def T_and_run() -> tuple[Execution, Execution]:
        # source: ONE merged request
        env_m = E.fresh_env(suite, ct)
        pre_m = env_m.model_copy(deep=True)
        src = agent_exec(suite, ct.PROMPT, env_m, "merged")
        src.u = ct.utility(src.m, pre_m, src.s_post, strict=False)

        # follow-up: TWO consecutive requests, same session/environment
        env_s = E.fresh_env(suite, ct)
        pre_s = env_s.model_copy(deep=True)
        e1 = agent_exec(suite, t1.PROMPT, env_s, "split-1")
        e2 = agent_exec(suite, t2.PROMPT, e1.s_post, "split-2")
        u1 = t1.utility(e1.m, pre_s, e2.s_post, strict=False)
        u2 = t2.utility(e2.m, pre_s, e2.s_post, strict=False)
        e2.u = u1 and u2
        print(f"    utility: merged={src.u}   part1={u1} & part2={u2} -> {e2.u}")
        return src, e2

    def pi(ex: Execution):
        """pi : (task utility, final state modulo ids + wall-clock, did-write flag).

        Projects s_post, NOT the trace: the two runs legitimately differ in tool calls
        (the split run made an extra get_current_day call) while reaching the same state.

        The did-write flag guards vacuity, exactly as MR-A's well_formed does: if both
        subgoals are read-only, "the two final states are equal" holds because nothing
        ever changed, and a PASS would mean nothing. Such pairs report INCONCLUSIVE.
        """
        before, after = canon(ex.s_pre, ("id_", "id")), canon(ex.s_post, ("id_", "id"))
        return (ex.u, after, before != after)

    def R(v_src, v_fup) -> bool:
        """R : utilities agree AND final task-relevant states are equal."""
        return v_src[0] == v_fup[0] and v_src[1] == v_fup[1]

    return MR(
        id=f"B-{domain}-merge/{combined}", family="non-interference", domain=domain,
        level=Level.AGENT,
        statement="Two unrelated requests handled together leave the same state as handled "
                  "one after another.",
        evidence=f"{domain}/user_tasks.py combined {combined} = {p1} + {p2}",
        run=T_and_run, projection=pi, relation=R,
        well_formed=lambda v: v[2],  # an execution that wrote nothing cannot be judged
        modulo=("id", "id_", "timestamp", "last_modified"),
    )


# ===========================================================================

def report(mr: MR, extra=None) -> Verdict:
    print(f"\n{'=' * 78}\n{mr.id}   [{mr.family}]   level={mr.level}")
    print(f"  property : {mr.statement}")
    print(f"  evidence : {mr.evidence}")
    if mr.modulo:
        print(f"  mod      : ignoring {', '.join(mr.modulo)}")
    res = mr.check()
    print(f"\n  --> {res.verdict.upper()}")
    if res.verdict is Verdict.VIOLATION:
        from deepdiff import DeepDiff
        a, b = res.src_view, res.fup_view
        if isinstance(a, tuple):  # MR-B projection: (utility, state, wrote)
            if a[0] != b[0]:
                print(f"      utility differs: merged={a[0]} vs split={b[0]}")
            d = DeepDiff(a[1], b[1], ignore_order=True)
            for kind, items in d.items():
                print(f"      {kind}:")
                keys = items.keys() if hasattr(items, "keys") else range(len(items))
                for k in list(keys)[:6]:
                    print(f"         {str(k)[:150]}")
                    v = items[k] if hasattr(items, "keys") else items[k]
                    print(f"           {str(v)[:300]}")
        else:
            print(f"      {res.detail}")
    return res.verdict


# Shipped combined pairs that are usable as merge<->split instances.
# Excluded, with reasons established by running the checkers:
#   workspace user_task_23 (= ut1+ut22), user_task_39 (= ut16+ut22)
#       -> both subgoals read-only; "states are equal" holds because nothing was ever
#          written, so a PASS is uninformative. The well_formed guard reports INCONCLUSIVE.
#   slack user_task_18, user_task_19
#       -> their merged prompt is "do all the tasks on my TODO list at <url>", so the agent
#          must first fetch a webpage to discover the subgoals, while the split prompts state
#          them outright. That confounds merge-vs-split with retrieval-vs-stated.
MR_B_PAIRS = [
    ("workspace", "user_task_4", "user_task_1", "user_task_6"),
    ("workspace", "user_task_19", "user_task_1", "user_task_13"),
    ("workspace", "user_task_36", "user_task_30", "user_task_31"),
    ("workspace", "user_task_37", "user_task_30", "user_task_32"),
    ("workspace", "user_task_38", "user_task_27", "user_task_35"),
    ("slack", "user_task_17", "user_task_0", "user_task_2"),
    ("slack", "user_task_20", "user_task_15", "user_task_16"),
]


def all_mr_b() -> list[MR]:
    return [mr_b(*spec) for spec in MR_B_PAIRS]


if __name__ == "__main__":
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("set OPENAI_API_KEY  (OPENAI_API_KEY=$(cat ~/openai.key) python level_a.py)")
    print(f"LEVEL A -- agent-output metamorphic tests   model={MODEL}")
    print("AgentDojo: no user simulator; single-shot PROMPT + agent tool-calling loop.")

    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    mrs = (all_mr_a() if only in ("all", "a") else []) + \
          (all_mr_b() if only in ("all", "b") else [])
    results = [(m, report(m)) for m in mrs]

    print("\n" + "=" * 78)
    print("SUMMARY")
    for m, v in results:
        print(f"  {v.upper():<13} {m.id:<34} [{m.family}]")
    tally = collections.Counter(v for _, v in results)
    print("  " + "   ".join(f"{k}={n}" for k, n in tally.items()))
