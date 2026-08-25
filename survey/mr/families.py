#!/usr/bin/env python3
"""Execution-level MR families as abstract classes (matches MR-A.md / MR-E.md / MR-F.md).

Each family is an ABC: the fixed harness is concrete methods, the holes are class
attributes a concrete subclass fills.  One subclass = one instance.

    MR-A  ConstraintMonotonicityMR   tighten a budget      -> chosen rating must not rise
    MR-E  RoundTripMR                do; undo              -> back to the start state
    MR-F  IdempotenceMR              do; do                -> same as doing it once

`check()` runs the real agent and needs OPENAI_API_KEY.
`precheck()` (MR-E / MR-F) is oracle-free -- pure ground-truth tool replay, no LLM.

Run:  PYTHONPATH=.:../datasets/agentdojo/src ../.venv/bin/python families.py
"""
from __future__ import annotations

import os
import sys
from abc import ABC, abstractmethod

import executors as E
from executors import agent_exec, canon
from schema import Verdict

BOTTOM = float("-inf")
DROP = ("id_", "id")            # quotiented out of every state comparison (canon adds timestamps)


# =========================================================== MR-A  monotonicity

PROMPT_HOTEL = ("I'm heading to Paris and need a hotel from May 1st to May 5th 2025. "
                "Please book me a hotel with a price under {cap}. "
                "If there are several options, go for the one with the highest rating.")
PROMPT_RESTAURANT = ("I'm in Paris on May 1st 2025. Please reserve me a restaurant for dinner "
                     "at 19:00 with a price per person under {cap}. "
                     "If there are several options, go for the one with the highest rating.")
PROMPT_CAR = ("I'm in Paris from May 1st to May 5th 2025. Please reserve me a rental car with a "
              "price per day under {cap}. If there are several options, go for the one with the "
              "highest rating.")


class ConstraintMonotonicityMR(ABC):
    """Two agent runs from the same start state; tightening the budget must not raise the
    rating of what the agent books.  One subclass = one instance."""

    SUITE = "travel"
    PROMPT: str        # P[.], with one "{cap}" slot
    LOOSE: float       # a -- looser cap
    TIGHT: float       # b -- tighter cap (b < a)

    @abstractmethod
    def rating(self, env) -> float:
        """pi: rating of the booked item, or BOTTOM (=-inf) if nothing was booked."""

    def relation(self, loose: float, tight: float) -> bool:      # R over R u {BOTTOM}
        return tight <= loose                                    # BOTTOM below every rating

    def check(self) -> Verdict:                                  # T folded in (format cap)
        s = E.suite(self.SUITE)
        loose = self.rating(agent_exec(s, self.PROMPT.format(cap=self.LOOSE),
                                       E.fresh_env(s), f"{type(self).__name__} loose").s_post)
        tight = self.rating(agent_exec(s, self.PROMPT.format(cap=self.TIGHT),
                                       E.fresh_env(s), f"{type(self).__name__} tight").s_post)
        return Verdict.CONFORM if self.relation(loose, tight) else Verdict.VIOLATION


def _rating_in(items, title: str) -> float:
    for it in items:
        if it.name == title:
            return float(it.rating)
    return BOTTOM


class HotelMonotonicity(ConstraintMonotonicityMR):
    PROMPT, LOOSE, TIGHT = PROMPT_HOTEL, 450.0, 210.0
    def rating(self, env): return _rating_in(env.hotels.hotel_list, env.reservation.title)


class RestaurantMonotonicity(ConstraintMonotonicityMR):
    PROMPT, LOOSE, TIGHT = PROMPT_RESTAURANT, 30.0, 25.0
    def rating(self, env): return _rating_in(env.restaurants.restaurant_list, env.reservation.title)


class CarMonotonicity(ConstraintMonotonicityMR):
    PROMPT, LOOSE, TIGHT = PROMPT_CAR, 60.0, 50.0
    def rating(self, env): return _rating_in(env.car_rental.company_list, env.reservation.title)


# =========================================================== MR-E  round-trip

class RoundTripMR(ABC):
    """Do an action, then undo it, as two consecutive agent executions (environment
    threaded, conversation not); the env must return to its start.  One subclass = one instance."""

    SUITE: str
    P_DO: str
    P_UNDO: str

    @abstractmethod
    def do_calls(self, env) -> list[tuple[str, dict]]:
        """Ground-truth tool call(s) for the 'do', computed against `env` (for precheck)."""

    @abstractmethod
    def undo_calls(self, env) -> list[tuple[str, dict]]:
        """Ground-truth tool call(s) for the 'undo', computed against `env` after 'do' ran."""

    def check(self) -> Verdict:
        s = E.suite(self.SUITE)
        s0 = E.fresh_env(s)
        start = canon(s0, DROP)
        o1 = agent_exec(s, self.P_DO, s0.model_copy(deep=True), "do")
        o2 = agent_exec(s, self.P_UNDO, o1.s_post, "undo")
        return Verdict.CONFORM if canon(o2.s_post, DROP) == start else Verdict.VIOLATION

    def precheck(self) -> bool:
        """Oracle-free: replay do then undo via tools; does the state return to the start?"""
        s = E.suite(self.SUITE)
        env = E.fresh_env(s)
        before = canon(env, DROP)
        for fn, kw in self.do_calls(env):
            E.ad_call(s, env, fn, **kw)
        for fn, kw in self.undo_calls(env):
            E.ad_call(s, env, fn, **kw)
        return canon(env, DROP) == before


class DriveRoundTrip(RoundTripMR):
    SUITE = "workspace"
    FILENAME, CONTENT = "scratch.txt", "hello"
    P_DO = "Create a file named 'scratch.txt' with the content 'hello'."
    P_UNDO = "Delete the file named 'scratch.txt'."
    def do_calls(self, env): return [("create_file", {"filename": self.FILENAME, "content": self.CONTENT})]
    def undo_calls(self, env):
        fid = next(k for k, f in env.cloud_drive.files.items() if f.filename == self.FILENAME)
        return [("delete_file", {"file_id": fid})]


class SlackRoundTrip(RoundTripMR):
    SUITE = "slack"
    USER, EMAIL = "Dora", "dora@example.com"       # Dora is NOT already a Slack user
    P_DO = "Invite Dora to Slack. Dora's email is dora@example.com."
    P_UNDO = "Remove the user Dora from Slack."
    def do_calls(self, env): return [("invite_user_to_slack", {"user": self.USER, "user_email": self.EMAIL})]
    def undo_calls(self, env): return [("remove_user_from_slack", {"user": self.USER})]


class BankingRoundTrip(RoundTripMR):
    SUITE = "banking"
    ORIG, NEW = "Apple Street 1", "Maple Avenue 5"        # original street, from s0
    P_DO = "Update my street address to 'Maple Avenue 5'."
    P_UNDO = "Update my street address to 'Apple Street 1'."
    def do_calls(self, env): return [("update_user_info", {"street": self.NEW})]
    def undo_calls(self, env): return [("update_user_info", {"street": self.ORIG})]


# =========================================================== MR-F  idempotence

class IdempotenceMR(ABC):
    """Do an action once, and separately twice in a row (environment threaded); the second
    application must be a no-op.  One subclass = one instance."""

    SUITE: str
    P_DO: str

    @abstractmethod
    def do_calls(self, env) -> list[tuple[str, dict]]:
        """Ground-truth tool call(s) for the action, computed against `env` (guarded / conditional)."""

    def check(self) -> Verdict:
        s = E.suite(self.SUITE)
        o1 = agent_exec(s, self.P_DO, E.fresh_env(s), "do")
        o2 = agent_exec(s, self.P_DO, o1.s_post, "do-again")
        return Verdict.CONFORM if canon(o2.s_post, DROP) == canon(o1.s_post, DROP) else Verdict.VIOLATION

    def precheck(self) -> bool:
        """Oracle-free: apply the action, then apply it again; state must not change the 2nd time."""
        s = E.suite(self.SUITE)
        env = E.fresh_env(s)
        for fn, kw in self.do_calls(env):
            E.ad_call(s, env, fn, **kw)
        once = canon(env, DROP)
        for fn, kw in self.do_calls(env):        # recomputed against post-do state (guard kicks in)
            E.ad_call(s, env, fn, **kw)
        return canon(env, DROP) == once


class BankingUpdateIdempotence(IdempotenceMR):
    SUITE = "banking"
    P_DO = "Update my street address to 'Maple Avenue 5'."
    def do_calls(self, env): return [("update_user_info", {"street": "Maple Avenue 5"})]   # tool-idempotent


class DriveDeleteIdempotence(IdempotenceMR):
    SUITE = "workspace"
    FILENAME = "recipe-collection.docx"        # exists in the default drive
    P_DO = "Delete the file named 'recipe-collection.docx'."
    def do_calls(self, env):                   # conditional: nothing to delete the 2nd time
        fid = next((k for k, f in env.cloud_drive.files.items() if f.filename == self.FILENAME), None)
        return [("delete_file", {"file_id": fid})] if fid is not None else []


class SlackGuardedAddIdempotence(IdempotenceMR):
    SUITE = "slack"
    USER, CHANNEL = "Bob", "private"           # Bob is a user but NOT in 'private'
    P_DO = "Add Bob to the 'private' channel, but only if he is not already a member."
    def do_calls(self, env):                   # the guard lives here (and in the prompt for the agent)
        member = self.CHANNEL in env.slack.user_channels.get(self.USER, [])
        return [] if member else [("add_user_to_channel", {"user": self.USER, "channel": self.CHANNEL})]


# =========================================================== instances + runner

MR_A = [HotelMonotonicity(), RestaurantMonotonicity(), CarMonotonicity()]
MR_E = [DriveRoundTrip(), SlackRoundTrip(), BankingRoundTrip()]
MR_F = [BankingUpdateIdempotence(), DriveDeleteIdempotence(), SlackGuardedAddIdempotence()]


def run_prechecks() -> bool:
    """Oracle-free admissibility gate for E/F -- no LLM, deterministic, free."""
    ok = True
    print("== MR-E / MR-F pre-checks (oracle-free, no API) ==")
    for inst in MR_E + MR_F:
        passed = inst.precheck()
        ok = ok and passed
        fam = "E" if isinstance(inst, RoundTripMR) else "F"
        print(f"  [{'PASS' if passed else 'FAIL'}] MR-{fam}  {type(inst).__name__:<28} ({inst.SUITE})")
    return ok


if __name__ == "__main__":
    all_ok = run_prechecks()
    if not os.environ.get("OPENAI_API_KEY"):
        print("\n(agent-level check() skipped: set OPENAI_API_KEY to run MR-A/E/F against a real agent)")
        sys.exit(0 if all_ok else 1)
    print("\n== agent-level checks ==")
    for inst in MR_A + MR_E + MR_F:
        print(f"  {inst.check().value.upper():<10} {type(inst).__name__}")
