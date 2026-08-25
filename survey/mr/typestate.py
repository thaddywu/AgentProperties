#!/usr/bin/env python3
"""
Action-based typestate checking of ToolBench traces.

A typestate machine is written BY HAND from a tool's static specification
(`toolenv/tools/<Category>/<tool>.json`) -- never inferred from traces. It is then
replayed against already-collected traces to find calls the machine forbids.

    FSM  = < resources, edges >          hand-written, one per tool
    edge = < op, src states, dst, instance key, guard, produces >

Transitions are keyed on the OPERATION (the endpoint name), which is what a trace
records. They are NOT derived from URLs: in this corpus a URL is not unique per
operation (sms77io `Create Contact` and `Edit Contact` share one URL, and
`Delete Contact` is the bare `/contacts` distinguished only by an `action` argument).


UNIT OF CHECKING: ONE ROOT-TO-LEAF PATH
---------------------------------------
ToolBench runs DFSDT, so `answer_generation.tree` is a search tree, not one agent
execution. The only history that ever existed inside the agent's context window is the
path from the root to the node it is expanding, so that path is the unit we check. One
trace yields many such runs (sms77io: median 19 leaf paths per trace, 15 after
deduplicating identical call sequences; each path 4-6 calls, hard-capped at 6).

`answer_generation.train_messages[-1]` is exactly ONE of those paths -- the last one --
which is why counting calls there understates how much is in a trace.

A pre-order traversal of the whole tree is deliberately NOT offered. It would fuse
sibling subtrees into a single history the agent never had. It is also not a sound
reconstruction of real server state: ToolBench calls a shared live RapidAPI backend, so
whether a given resource exists depends on other tasks and other months. Real server
state is not recoverable offline at all, which leaves the agent-epistemic reading as the
only well-defined one.


IDENTIFIER LEDGER
-----------------
State is a map (resource, instance_key) -> state, plus a LEDGER of identifier values the
agent could legitimately have known. The ledger separates two failures that look
identical if you only track states:

    UNBOUND_IDENTIFIER    the agent passed an id that no response it could see ever
                          returned (fabricated argument)
    UNDEFINED_TRANSITION  the id is real but the resource is not in a state that
                          admits this operation (genuine ordering violation)

State transitions come only from the path's own calls. The ledger additionally absorbs
the sibling alternatives DFSDT injects when it backtracks, because that prompt carries
their `function_output` verbatim:

    "This is not the first time you try this task, all previous trails failed. ...
     Here are some previous actions candidates: [{"name": ..., "arguments": ...,
     "function_output": "{\"error\": \"\", \"response\": ...}"}]"

An id the agent was shown there is not fabricated, so counting it would be a false
accusation. `--ledger path` turns this off to measure how much it matters.

Run:
    python typestate.py --tool sms77io --limit 50
    python typestate.py --tool sms77io --jsonl /tmp/findings.jsonl
    python typestate.py --tool sms77io --trace \
        ../datasets/ToolBench/data/answer/G1_answer/40436_ChatGPT_DFS_woFilter_w2.json
"""

from __future__ import annotations

import argparse
import ast
import collections
import json
import os
import re
import sys
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parent.parent / "datasets" / "ToolBench" / "data"

ABSENT = "ABSENT"  # implicit initial state of every instance; provenance: prior knowledge


# ===========================================================================
# Findings
# ===========================================================================


class Kind(StrEnum):
    UNBOUND_IDENTIFIER = "UNBOUND_IDENTIFIER"
    UNDEFINED_TRANSITION = "UNDEFINED_TRANSITION"
    GUARD_UNSATISFIED = "GUARD_UNSATISFIED"
    UNREACHABLE_PRECONDITION = "UNREACHABLE_PRECONDITION"
    UNKNOWN_OPERATION = "UNKNOWN_OPERATION"  # hallucinated endpoint, not an FSM violation


FSM_KINDS = (
    Kind.UNBOUND_IDENTIFIER,
    Kind.UNDEFINED_TRANSITION,
    Kind.GUARD_UNSATISFIED,
    Kind.UNREACHABLE_PRECONDITION,
)


@dataclass
class Finding:
    kind: Kind
    op: str
    resource: str | None
    instance: str | None
    observed_state: str | None
    expected_states: tuple[str, ...] | None
    call_index: int  # position within the path
    expand_num: int | None  # ToolBench's global expansion counter
    args_excerpt: str
    detail: str
    trace: str
    path_id: int
    path_ops: tuple[str, ...]  # the whole path, for reading the finding in context

    def as_dict(self) -> dict[str, Any]:
        d = dict(self.__dict__)
        d["kind"] = str(self.kind)
        d["expected_states"] = list(self.expected_states or ())
        d["path_ops"] = list(self.path_ops)
        return d


# ===========================================================================
# FSM specification
# ===========================================================================


@dataclass(frozen=True)
class Edge:
    """One action-based transition.

    op          endpoint name, exactly as it appears in the spec's `api_list` `name`
    resource    which resource's state this operation moves
    src         source states the operation is defined on; ABSENT must be listed
                explicitly when creation from nothing is legal
    dst         destination state on a SUCCESSFUL call
    key_arg     argument naming the instance; None + key_from None => singleton "*"
    key_from    extract the instance key from the RESPONSE, for creates that mint an
                id server-side
    requires_bound
                key_arg's value must already be in the ledger; when it is not we report
                UNBOUND_IDENTIFIER and suppress UNDEFINED_TRANSITION, so one mistake
                produces one finding
    produces    response -> identifier values to add to the ledger
    guard       args -> (ok, message); false yields GUARD_UNSATISFIED
    guard_dst   state to move to when the guard fails but the call still had an effect
    unreachable_src
                src is enterable only through a transition that has no endpoint, so any
                use of this edge is UNREACHABLE_PRECONDITION
    read_only   the call does not change state (id-producing reads)
    note        provenance: which spec field the edge came from, quoted
    """

    op: str
    resource: str
    src: tuple[str, ...]
    dst: str
    key_arg: str | None = None
    key_from: Callable[[Any], list[str]] | None = None
    requires_bound: bool = False
    produces: Callable[[Any], list[str]] | None = None
    guard: Callable[[dict], tuple[bool, str]] | None = None
    guard_dst: str | None = None
    unreachable_src: bool = False
    read_only: bool = False
    note: str = ""


@dataclass
class Fsm:
    tool: str
    edges: tuple[Edge, ...]
    # Operations that exist in the spec but move no resource. Listed explicitly so that
    # anything neither here nor in `edges` is a hallucinated endpoint.
    stateless_ops: tuple[str, ...] = ()
    not_checkable: tuple[tuple[str, str], ...] = ()

    def by_op(self) -> dict[str, list[Edge]]:
        out: dict[str, list[Edge]] = collections.defaultdict(list)
        for e in self.edges:
            out[e.op].append(e)
        return dict(out)


# ===========================================================================
# Observation parsing
# ===========================================================================

_TRUNC_ERR = re.compile(r'^\{"error":\s*"((?:[^"\\]|\\.)*)"')


@dataclass
class Observation:
    error: str
    response: Any
    truncated: bool
    raw_body: str = ""
    """The response before parsing. Kept because seven.io returns its status code as
    plain text ("900\\n..."), and json.loads turns a bare "900" into an int, which would
    otherwise slip past the status-code check and be read as success."""

    @property
    def ok(self) -> bool | None:
        """True success, False failure, None undecidable (truncated / unknown code)."""
        if self.error:
            return False
        if self.response in ("", None):
            return False
        r = self.response
        if isinstance(r, dict):
            if r.get("success") is False:
                return False
            if "Fault" in r or "faultcode" in r:
                return False
            if r.get("type") == "error":
                return False
            if r.get("error") not in (None, "", False):
                return False
        head = ""
        if isinstance(self.raw_body, str) and self.raw_body.strip():
            head = self.raw_body.strip().splitlines()[0].strip().strip('"')
        elif isinstance(r, str) and r.strip():
            head = r.strip().splitlines()[0].strip()
        if re.fullmatch(r"\d{3}", head):
            # seven.io puts a numeric status code on the first line; 100 is success.
            return True if head == "100" else None
        if self.truncated:
            return None
        return True


def parse_observation(raw: str | None) -> Observation:
    """Observations are `{"error": ..., "response": "<python repr>"}`.

    The string is hard-truncated at 1027 characters, so about 30% are not valid JSON.
    Recover `error` by regex in that case and mark the result undecidable rather than
    reporting a failure that did not happen.
    """
    if not raw:
        return Observation(error="", response="", truncated=False)
    try:
        outer = json.loads(raw)
    except Exception:
        m = _TRUNC_ERR.match(raw)
        body = raw[m.end() :] if m else raw
        return Observation(
            error=m.group(1) if m else "",
            response=_inner(body),
            truncated=True,
            raw_body=body if isinstance(body, str) else "",
        )
    body = outer.get("response")
    return Observation(
        error=outer.get("error") or "",
        response=_inner(body),
        truncated=False,
        raw_body=body if isinstance(body, str) else "",
    )


def _inner(x: Any) -> Any:
    if not isinstance(x, str):
        return x
    s = x.strip()
    if not s:
        return ""
    for loader in (json.loads, ast.literal_eval):
        try:
            return loader(s)
        except Exception:
            pass
    return s


def _loose(s: str | None) -> dict[str, Any]:
    if not s:
        return {}
    for loader in (json.loads, ast.literal_eval):
        try:
            v = loader(s)
            return v if isinstance(v, dict) else {}
        except Exception:
            pass
    return {}


# ---- identifier extractors -------------------------------------------------


def walk_ids(obj: Any, keys: Sequence[str] = ("id", "ID", "Id", "msg_id")) -> list[str]:
    out: list[str] = []

    def rec(x: Any) -> None:
        if isinstance(x, dict):
            for k, v in x.items():
                if k in keys and isinstance(v, (str, int)) and str(v).strip():
                    out.append(str(v))
                else:
                    rec(v)
        elif isinstance(x, list):
            for v in x:
                rec(v)

    rec(obj)
    return out


def _lines(resp: Any) -> list[str]:
    if not isinstance(resp, str):
        return []
    return [ln.strip() for ln in resp.splitlines() if ln.strip()]


def second_line_id(resp: Any) -> list[str]:
    """`Create Contact` body is `"152\\n4980093"`; the id is on line 2."""
    ls = _lines(resp)
    if len(ls) >= 2 and re.fullmatch(r"\d+", ls[1]):
        return [ls[1]]
    return walk_ids(resp)


def csv_or_json_ids(resp: Any) -> list[str]:
    """`Get Contacts` returns CSV `"123456";"Tom Test";"+49..."` unless json=1."""
    if isinstance(resp, str):
        out = []
        for ln in _lines(resp):
            first = ln.split(";")[0].strip().strip('"')
            if re.fullmatch(r"\d+", first):
                out.append(first)
        return out
    return walk_ids(resp)


def truthy(v: Any) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


# ===========================================================================
# sms77io -- hand-written from the spec; see examples/toolbench/sms77io.md
# ===========================================================================

SMS77IO = Fsm(
    tool="sms77io",
    edges=(
        # ---- contact ---------------------------------------------------------
        Edge(
            op="Create Contact",
            resource="contact",
            src=(ABSENT,),
            dst="EXISTS",
            key_from=second_line_id,
            produces=second_line_id,
            note='prose "Creates a single contact for a given API key."; '
            'schema body "152\\n4980093" -> id on line 2',
        ),
        Edge(
            op="Get Contacts",
            resource="contact",
            src=(ABSENT, "EXISTS"),
            dst="EXISTS",
            read_only=True,
            produces=csv_or_json_ids,
            note='prose "Retrieves all contacts for a given API key."; '
            "schema items.properties.ID",
        ),
        Edge(
            op="Edit Contact",
            resource="contact",
            src=("EXISTS",),
            dst="EXISTS",
            key_arg="id",
            requires_bound=True,
            note='prose "Edit a contact with a given ID."',
        ),
        Edge(
            op="Delete Contact",
            resource="contact",
            src=("EXISTS",),
            dst=ABSENT,
            key_arg="id",
            requires_bound=True,
            note='prose "Deletes a single contact by ID for the given API key."',
        ),
        # ---- webhook ---------------------------------------------------------
        Edge(
            op="Create Webhook",
            resource="webhook",
            src=(ABSENT,),
            dst="SUBSCRIBED",
            key_from=walk_ids,
            produces=walk_ids,
            guard=lambda a: (
                a.get("event_type") in (None, "")
                or str(a["event_type"]) in ("sms_mo", "dlr", "voice_status"),
                "event_type must be sms_mo|dlr|voice_status "
                "(schema: Get Webhooks properties.event_type pattern)",
            ),
            note='prose "Creates a webhook with the given configuration."; '
            "schema properties.id, required=[success]",
        ),
        Edge(
            op="Get Webhooks",
            resource="webhook",
            src=(ABSENT, "SUBSCRIBED"),
            dst="SUBSCRIBED",
            read_only=True,
            produces=walk_ids,
            note='prose "Retrieves all existing webhooks."; schema hooks[].id',
        ),
        Edge(
            op="Delete Webhook",
            resource="webhook",
            src=("SUBSCRIBED",),
            dst=ABSENT,
            key_arg="id",
            requires_bound=True,
            note='prose "Deletes the webhook with the given ID."',
        ),
        # ---- subaccount (singleton: no identifier exposed, and no delete exists) ----
        Edge(
            op="Create",
            resource="subaccount",
            src=(ABSENT, "EXISTS"),
            dst="EXISTS",
            guard=lambda a: (
                a.get("action") in (None, "", "create"),
                'action must be "create" (schema: required parameter default "create")',
            ),
            guard_dst="EXISTS",
            note='prose "Creates a new subaccount."',
        ),
        Edge(
            op="Read",
            resource="subaccount",
            src=(ABSENT, "EXISTS"),
            dst="EXISTS",
            read_only=True,
            note='prose "Retrieves information regarding subacounts."',
        ),
        # ---- sms message -----------------------------------------------------
        # One operation, two destinations, selected by ARGUMENT VALUE: without
        # return_msg_id / json / details the message is sent but its id is never
        # observable, so no later Get Status can name it.
        Edge(
            op="Send SMS",
            resource="sms",
            src=(ABSENT,),
            dst="SENT",
            key_from=lambda r: walk_ids(r) or second_line_id(r),
            produces=lambda r: walk_ids(r) or second_line_id(r),
            guard=lambda a: (
                truthy(a.get("return_msg_id")) or truthy(a.get("json")) or truthy(a.get("details")),
                "message is sent but no msg_id is returned -- prose (Get Status "
                'parameter msg_id): "Can be obtained by setting parameter JSON, '
                'return_msg_id or details to 1 when sending SMS via the API."',
            ),
            guard_dst="SENT_NO_ID",
            note="prose: Get Status parameter msg_id description",
        ),
        Edge(
            op="Get Status",
            resource="sms",
            src=("SENT",),
            dst="REPORTED",
            key_arg="msg_id",
            requires_bound=True,
            note='prose "Get a delivery report for a message ID sent with your API key."',
        ),
        # Journals recover ids for messages sent without return_msg_id -- prose
        # (Get Status parameter msg_id): "Alternatively it can be retrieved from the
        # message journal in the user area."
        *[
            Edge(
                op=op,
                resource="sms",
                src=(ABSENT, "SENT", "SENT_NO_ID", "REPORTED"),
                dst="SENT",
                read_only=True,
                produces=walk_ids,
                note=f'prose "{desc}"; recovers msg_id from the journal',
            )
            for op, desc in (
                ("Outbound", "Retrieves outbound messages history."),
                ("Inbound", "Retrieves inbound messages history."),
                ("Replies", "Retrieves message replies history."),
            )
        ],
        # ---- caller id -------------------------------------------------------
        Edge(
            op="Validate Caller ID",
            resource="caller_id",
            src=(ABSENT, "UNVERIFIED", "PENDING_DTMF"),
            dst="PENDING_DTMF",
            key_arg="number",
            note='prose "After calling this endpoint you will get a code back if '
            "successful. At the same time, the phone number is going to receive a call "
            'from us."',
        ),
        # VERIFIED is entered only by typing the code on a telephone keypad. No endpoint
        # performs that transition, so an agent can never legally reach it.
        Edge(
            op="Send Voice Call",
            resource="caller_id",
            src=("VERIFIED",),
            dst="VERIFIED",
            key_arg="from",
            unreachable_src=True,
            note='prose "The returned code must then be entered via DTMF using the '
            "telephone's keypad.\" + Send Voice Call parameter from: \"Please use only "
            "verified sender IDs, one of your virtual inbound numbers or one of our "
            'shared virtual numbers."',
        ),
        Edge(
            op="Voice",
            resource="caller_id",
            src=(ABSENT, "UNVERIFIED", "PENDING_DTMF", "VERIFIED"),
            dst="UNVERIFIED",
            read_only=True,
            note='prose "Retrieves voice messages history."',
        ),
    ),
    stateless_ops=(
        "Home Location Register",
        "Caller Name Delivery",
        "Mobile Number Portability",
        "Number Format Lookup",
        "Get Pricing",
        "Get Balance",
        "Get Analytics",
    ),
    not_checkable=(
        (
            "Send SMS reload lock",
            "prose (Send SMS parameter no_reload): the same text/type/recipient must "
            "not be resent within 180 seconds unless no_reload is set. ToolBench "
            "records no per-call timestamps, so the window cannot be evaluated.",
        ),
        (
            "Caller ID DTMF confirmation",
            "the PENDING_DTMF -> VERIFIED transition happens on a telephone keypad and "
            "leaves no trace record, so VERIFIED can never be observed as reached; "
            "every Send Voice Call carrying `from` is reported as "
            "UNREACHABLE_PRECONDITION by construction.",
        ),
    ),
)

FSMS: dict[str, Fsm] = {"sms77io": SMS77IO}


# ===========================================================================
# Operation-name normalisation
# ===========================================================================


def standardize(name: str) -> str:
    """Reproduce ToolBench's normalisation: "Get Status" -> "get_status"."""
    s = re.sub(r"[^a-zA-Z0-9\s_]", "", name)
    s = re.sub(r"[\s_]+", "_", s).strip("_").lower()
    return "get_" + s if s and s[0].isdigit() else s


def op_index(tool: str, spec_path: Path) -> dict[str, str]:
    """trace function name -> endpoint name in the spec."""
    spec = json.loads(spec_path.read_text())
    tool_key = standardize(spec.get("tool_name") or tool)
    idx: dict[str, str] = {}
    for api in spec["api_list"]:
        fn = f"{standardize(api['name'])}_for_{tool_key}"
        idx[fn] = api["name"]
        idx.setdefault(fn[:64], api["name"])  # ToolBench truncates names at 64 chars
    return idx


def find_spec(tool: str) -> Path:
    hits = sorted((DATA / "toolenv" / "tools").glob(f"*/{standardize(tool)}.json"))
    if not hits:
        raise SystemExit(f"no spec for tool {tool!r} under {DATA / 'toolenv' / 'tools'}")
    return hits[0]


# ===========================================================================
# Path extraction
# ===========================================================================


@dataclass
class Call:
    op_raw: str
    args: dict[str, Any]
    obs: Observation
    index: int
    expand_num: int | None
    # Sibling alternatives already tried at this state, injected into the agent's
    # context by DFSDT's backtrack prompt together with their function_output.
    visible_siblings: tuple[Observation, ...] = ()


def _action_call(node: dict, index: int, siblings: tuple[Observation, ...]) -> Call:
    kids = node.get("children") or []
    inp = kids[0] if kids and kids[0].get("node_type") == "Action Input" else {}
    return Call(
        op_raw=node.get("description") or "",
        args=_loose(inp.get("description")),
        obs=parse_observation(inp.get("observation")),
        index=index,
        expand_num=inp.get("expand_num"),
        visible_siblings=siblings,
    )


def _is_action(node: dict) -> bool:
    return node.get("node_type") == "Action"


def leaf_paths(answer: dict) -> list[list[Call]]:
    """Every root-to-leaf path, deduplicated by (op, args) sequence.

    At each branch point the agent that expanded child k had already been shown children
    0..k-1 together with their outputs, so those observations ride along on the call as
    `visible_siblings`. Note the tree alternates
    Action -> Action Input -> (Action | Thought -> Action), so an Action is not always a
    direct child of an Action Input; recursion therefore descends through every child
    regardless of node_type.
    """
    tree = (answer.get("tree") or {}).get("tree")
    if not tree:
        return []
    paths: list[list[Call]] = []

    def rec(node: dict, acc: list[Call], siblings: tuple[Observation, ...]) -> None:
        acc2 = acc
        if _is_action(node):
            acc2 = acc + [_action_call(node, len(acc), siblings)]
        kids = node.get("children") or []
        if not kids:
            if acc2:
                paths.append(acc2)
            return
        seen: list[Observation] = []
        for c in kids:
            rec(c, acc2, tuple(seen))
            if _is_action(c):
                inp = (c.get("children") or [{}])[0]
                seen.append(parse_observation(inp.get("observation")))

    rec(tree, [], ())
    out: list[list[Call]] = []
    sigs: set[tuple] = set()
    for p in paths:
        sig = tuple((c.op_raw, json.dumps(c.args, sort_keys=True)) for c in p)
        if sig in sigs:
            continue
        sigs.add(sig)
        out.append(p)
    return out


# ===========================================================================
# Checker
# ===========================================================================


class Checker:
    def __init__(self, fsm: Fsm, ops: dict[str, str], use_siblings: bool = True):
        self.fsm = fsm
        self.ops = ops
        self.edges = fsm.by_op()
        self.use_siblings = use_siblings
        self.resources = {e.resource for e in fsm.edges}
        # A G2/G3 task exposes several tools, so most unresolved names simply belong to
        # another tool. Only a name that claims THIS tool and is absent from its spec is
        # a hallucinated endpoint.
        self.suffix = f"_for_{standardize(fsm.tool)}"

    def claims_tool(self, raw: str) -> bool:
        return raw.endswith(self.suffix)

    def resolve(self, raw: str) -> str | None:
        return self.ops.get(raw) or self.ops.get(raw[:64])

    def run(self, path: Sequence[Call], trace: str, path_id: int) -> list[Finding]:
        state: dict[tuple[str, str], str] = {}
        ledger: dict[str, set[str]] = collections.defaultdict(set)
        found: list[Finding] = []
        path_ops = tuple(c.op_raw for c in path)

        for call in path:
            op = self.resolve(call.op_raw)
            if op is None:
                if self.claims_tool(call.op_raw):
                    found.append(
                        _mk(
                            Kind.UNKNOWN_OPERATION,
                            call,
                            trace,
                            path_id,
                            path_ops,
                            detail=f"{call.op_raw!r} is not in the tool specification",
                        )
                    )
                continue

            # Absorb identifiers the agent was shown in sibling alternatives before it
            # issued this call. Every resource gets them: an id inside a foreign response
            # cannot be attributed to one resource, and over-crediting only makes
            # UNBOUND_IDENTIFIER more conservative.
            if self.use_siblings:
                for sib in call.visible_siblings:
                    if sib.ok is not False:
                        for v in walk_ids(sib.response) + second_line_id(sib.response):
                            for res in self.resources:
                                ledger[res].add(str(v))

            for edge in self.edges.get(op, ()):
                self._step(edge, call, state, ledger, found, trace, path_id, path_ops)
        return found

    def _step(
        self,
        edge: Edge,
        call: Call,
        state: dict[tuple[str, str], str],
        ledger: dict[str, set[str]],
        found: list[Finding],
        trace: str,
        path_id: int,
        path_ops: tuple[str, ...],
    ) -> None:
        ok = call.obs.ok

        # ---- guard on argument values (evaluated even when the call failed) ----
        if edge.guard is not None:
            good, msg = edge.guard(call.args)
            if not good:
                found.append(
                    _mk(
                        Kind.GUARD_UNSATISFIED,
                        call,
                        trace,
                        path_id,
                        path_ops,
                        edge=edge,
                        detail=msg,
                    )
                )
                if edge.guard_dst is not None and ok is not False:
                    state[(edge.resource, f"<anon#{call.index}>")] = edge.guard_dst
                return

        # ---- which instance does this call name? -------------------------------
        if edge.key_arg is not None:
            raw = call.args.get(edge.key_arg)
            if raw in (None, ""):
                return  # identifying argument absent -> edge inapplicable
            key = str(raw)
        elif edge.key_from is not None:
            keys = edge.key_from(call.obs.response) if ok is not False else []
            key = keys[0] if keys else f"<new#{call.index}>"
        else:
            key = "*"

        st = state.get((edge.resource, key), ABSENT)

        # ---- source state has no API transition into it ------------------------
        if edge.unreachable_src:
            found.append(
                _mk(
                    Kind.UNREACHABLE_PRECONDITION,
                    call,
                    trace,
                    path_id,
                    path_ops,
                    edge=edge,
                    instance=key,
                    observed=st,
                    detail="required source state "
                    + "|".join(edge.src)
                    + " has no API transition into it; "
                    + edge.note,
                )
            )
            return

        # ---- fabricated identifier --------------------------------------------
        if edge.requires_bound and key not in ledger[edge.resource]:
            found.append(
                _mk(
                    Kind.UNBOUND_IDENTIFIER,
                    call,
                    trace,
                    path_id,
                    path_ops,
                    edge=edge,
                    instance=key,
                    observed=st,
                    detail=f"{edge.key_arg}={key!r} was never returned by any response "
                    f"visible to the agent for resource {edge.resource!r}",
                )
            )
            return  # one mistake, one finding: do not also blame the ordering

        # ---- ordering ----------------------------------------------------------
        if st not in edge.src:
            found.append(
                _mk(
                    Kind.UNDEFINED_TRANSITION,
                    call,
                    trace,
                    path_id,
                    path_ops,
                    edge=edge,
                    instance=key,
                    observed=st,
                    detail=f"operation is defined on {'|'.join(edge.src)}; "
                    f"{edge.resource}({key}) is in {st}",
                )
            )
            return

        # ---- apply -------------------------------------------------------------
        if ok is False:
            return  # a failed call leaves the resource where it was
        if not edge.read_only or st == ABSENT:
            state[(edge.resource, key)] = edge.dst
        if edge.produces is not None:
            for v in edge.produces(call.obs.response):
                ledger[edge.resource].add(str(v))
        if edge.key_from is not None and not key.startswith("<new#"):
            ledger[edge.resource].add(key)


def _mk(
    kind: Kind,
    call: Call,
    trace: str,
    path_id: int,
    path_ops: tuple[str, ...],
    *,
    edge: Edge | None = None,
    instance: str | None = None,
    observed: str | None = None,
    detail: str = "",
) -> Finding:
    return Finding(
        kind=kind,
        op=edge.op if edge else call.op_raw,
        resource=edge.resource if edge else None,
        instance=instance,
        observed_state=observed,
        expected_states=edge.src if edge else None,
        call_index=call.index,
        expand_num=call.expand_num,
        args_excerpt=json.dumps(call.args, ensure_ascii=False)[:160],
        detail=detail,
        trace=trace,
        path_id=path_id,
        path_ops=path_ops,
    )


# ===========================================================================
# Trace discovery
# ===========================================================================


def traces_for_tool(tool: str, limit: int | None = None) -> Iterator[Path]:
    """Answer files whose task exposed `tool` in its api_list."""
    n = 0
    for g in ("G1", "G2", "G3"):
        adir = DATA / "answer" / f"{g}_answer"
        qf = DATA / "instruction" / f"{g}_query.json"
        if not adir.is_dir() or not qf.is_file():
            continue
        have = set(os.listdir(adir))
        for e in json.loads(qf.read_text()):
            if not any(a["tool_name"] == tool for a in e["api_list"]):
                continue
            fn = f"{e['query_id']}_ChatGPT_DFS_woFilter_w2.json"
            if fn in have:
                yield adir / fn
                n += 1
                if limit and n >= limit:
                    return


# ===========================================================================
# CLI
# ===========================================================================


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--tool", default="sms77io", choices=sorted(FSMS))
    ap.add_argument("--trace", action="append", help="check specific answer file(s)")
    ap.add_argument("--limit", type=int, default=None, help="max traces to scan")
    ap.add_argument(
        "--ledger",
        default="path+siblings",
        choices=["path", "path+siblings"],
        help="whether ids shown in DFSDT's injected sibling candidates count as known",
    )
    ap.add_argument("--jsonl", help="write one JSON finding per line")
    ap.add_argument("--show", type=int, default=6, help="example findings to print")
    args = ap.parse_args(argv)

    fsm = FSMS[args.tool]
    checker = Checker(
        fsm, op_index(args.tool, find_spec(args.tool)), args.ledger.endswith("siblings")
    )

    files = (
        [Path(t) for t in args.trace]
        if args.trace
        else list(traces_for_tool(args.tool, args.limit))
    )
    print(f"tool={args.tool}  edges={len(fsm.edges)}  traces={len(files)}  ledger={args.ledger}")

    findings: list[Finding] = []
    kinds: collections.Counter = collections.Counter()
    ops_seen: collections.Counter = collections.Counter()
    n_traces = n_paths = n_calls = 0
    dirty_traces: set[str] = set()
    dirty_paths = 0
    sites: set[tuple[str, int | None, str]] = set()  # distinct violating API call sites
    own_calls = other_tool_calls = 0

    for fp in files:
        try:
            answer = json.loads(fp.read_text())
        except Exception:
            continue
        n_traces += 1
        for pid, path in enumerate(leaf_paths(answer)):
            n_paths += 1
            n_calls += len(path)
            for c in path:
                r = checker.resolve(c.op_raw)
                ops_seen[r or f"<unknown:{c.op_raw}>"] += 1
                if r is not None or checker.claims_tool(c.op_raw):
                    own_calls += 1
                elif c.op_raw != "Finish":
                    other_tool_calls += 1
            fs = checker.run(path, f"{fp.parent.name}/{fp.name}", pid)
            findings.extend(fs)
            for f in fs:
                kinds[f.kind] += 1
                sites.add((f.trace, f.expand_num, str(f.kind)))
            if any(f.kind in FSM_KINDS for f in fs):
                dirty_paths += 1
                dirty_traces.add(f"{fp.parent.name}/{fp.name}")

    print(f"\nparsed {n_traces} traces -> {n_paths} deduplicated leaf paths, {n_calls} calls")
    print(f"of those calls: {own_calls} belong to {args.tool}, "
          f"{other_tool_calls} to other tools exposed by the same task")
    print(f"distinct violating API call sites (trace, expand_num, kind): {len(sites)}")
    print(
        f"paths  with >=1 FSM violation: {dirty_paths}/{n_paths}"
        f" ({100 * dirty_paths / max(n_paths, 1):.1f}%)"
    )
    print(
        f"traces with >=1 FSM violation: {len(dirty_traces)}/{max(n_traces, 1)}"
        f" ({100 * len(dirty_traces) / max(n_traces, 1):.1f}%)\n"
    )

    print("findings by kind")
    for k, c in kinds.most_common():
        print(f"   {c:7d}  {k}")

    modelled = {e.op for e in fsm.edges}
    print("\ncalls by operation  (S = stateless in the FSM, - = not in the spec)")
    for op, c in ops_seen.most_common(20):
        tag = "  " if op in modelled else ("S " if op in fsm.stateless_ops else "- ")
        print(f"   {c:7d}  {tag}{op}")

    by_op = collections.Counter((f.op, str(f.kind)) for f in findings if f.kind in FSM_KINDS)
    if by_op:
        print("\nFSM violations by operation")
        for (op, kind), c in by_op.most_common(15):
            print(f"   {c:7d}  {op:22s} {kind}")

    if fsm.not_checkable:
        print("\nnot decidable from these traces")
        for name, why in fsm.not_checkable:
            print(f"   {name}: {why}")

    shown = [f for f in findings if f.kind in FSM_KINDS][: args.show]
    if shown:
        print(f"\n{len(shown)} example findings")
        for f in shown:
            print(
                f"  [{f.kind}] {f.trace} path={f.path_id} call#{f.call_index} "
                f"expand_num={f.expand_num}"
            )
            print(f"      path: {' -> '.join(f.path_ops)}")
            print(
                f"      op={f.op} resource={f.resource} instance={f.instance} "
                f"state={f.observed_state} expected={f.expected_states}"
            )
            print(f"      args={f.args_excerpt}")
            print(f"      {f.detail}")

    if args.jsonl:
        with open(args.jsonl, "w") as fh:
            for f in findings:
                fh.write(json.dumps(f.as_dict(), ensure_ascii=False) + "\n")
        print(f"\nwrote {len(findings)} findings to {args.jsonl}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
