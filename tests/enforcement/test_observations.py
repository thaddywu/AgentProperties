"""Shared observation facts retain types, authority and confirmed-effect semantics."""

from copy import deepcopy
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from policyweave.core.policy import (
    fact,
    policy_predicates,
    read_binding,
    validate_inputs,
    validate_state,
)
from policyweave.enforcement import BridgeError, FactTool, Policy
from policyweave.enforcement.edb import FactUpdates


def definition(type="symbol", cardinality="one", unit=None, observedAt=None):
    return dict(type=type, cardinality=cardinality, unit=unit, observedAt=observedAt)


CONTRACT = {"fields": {
    "principal": definition(cardinality="many"), "outcome": definition(), "owner": definition(),
    "input": definition(cardinality="many"), "calls": definition("number", unit="count"),
    "items": definition("number", unit="count", observedAt="observed_at"),
    "observed_at": definition("number", unit="unix_ms"),
}}


def binding():
    return dict(
        version=1,
        id="observation-test",
        context="Synthetic host observation contract.",
        mechanisms=["observations"],
        predicates=policy_predicates("", mechanisms=("observations",)),
        decision=dict(
            request="Request", parameters="Parameter", allow="Allow", deny="Deny"
        ),
        tests=[],
        observationContract=deepcopy(CONTRACT),
    )


class ObservationContractTests(unittest.TestCase):
    def test_numeric_units_and_identity_fields_fail_closed(self):
        b = read_binding(binding())
        validate_inputs(b, [fact("Field", "turn-a", "calls", 14)])
        for row in [
            fact("Field", "turn-a", "calls", "1.5"),
            fact("Field", "turn-a", "calls", "oops"),
            fact("Field", "turn-a", "calls", 2**63),
            fact("Field", "turn-a", "observed_at", "now"),
            fact("Event", "", "agent-a", "read"),
            fact("Event", "e1", " ", "read"),
            fact("Field", "e1", "", "value"),
        ]:
            with self.subTest(row=row), self.assertRaises(ValueError):
                validate_inputs(b, [row])
        for change in [dict(unit=""), dict(type="symbol", unit="count"), dict(observedAt="unknown")]:
            bad = binding()
            bad["observationContract"]["fields"]["calls"].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):read_binding(bad)
        with self.assertRaises(ValueError):validate_state(b, [fact("Field", "e1", "items", 1)])
        validate_state(b, [fact("Field", "e1", "items", 1), fact("Field", "e1", "observed_at", 1000)])
        with self.assertRaises(ValueError):validate_state(b, [fact("Field", "e1", "items", 1), fact("Field", "other", "observed_at", 1000)])

    def test_selected_shared_schema_cannot_weaken_types_keys_or_writers(self):
        for name, field, value in [
            ("Event", "key", []),
            ("Event", "appendOnly", False),
            ("Event", "hostOnly", False),
            ("Field", "hostOnly", False),
        ]:
            b = binding()
            b["predicates"][name][field] = value
            with self.subTest(name=name, field=field), self.assertRaises(ValueError):
                read_binding(b)
        for field in ("hostOnly", "appendOnly"):
            b = binding()
            b["predicates"]["Event"][field] = "true"
            with self.assertRaises(ValueError):
                read_binding(b)

    def test_fields_keep_cardinality_and_event_identity_is_append_only(self):
        edits = FactUpdates(binding(), [])
        edits.put("Field", "e1", "input", "a")
        edits.put("Field", "e1", "input", "b")
        self.assertEqual(len(edits.rows("Field")), 2)
        with self.assertRaises(ValueError):validate_state(binding(), [fact("Field", "turn-a", "calls", 1), fact("Field", "turn-a", "calls", 2)])
        edits.put("Event", "e1", "agent-a", "read")
        edits.put("Event", "e1", "agent-a", "read")
        with self.assertRaises(ValueError):
            edits.put("Event", "e1", "other", "read")
        with self.assertRaises(ValueError):
            edits.delete("Event", "e1")
        self.assertEqual(edits.rows("Event"), [("e1", "agent-a", "read")])


RULES = """Allow(Q) :- Request(Q, P, "observe"), Field("writers", "principal", P).
Allow(Q) :- Request(Q, P, "consume"), Parameter(Q, "event", E), Event(E, P, "observe"), Field(E, "outcome", "applied"), Field(E, "items", N), Field(E, "observed_at", At), N <= 2.
"""


@unittest.skipUnless(shutil.which("souffle"), "Native evaluator required")
class ObservationExecutionTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "rules.dl"
        self.path.write_text(RULES)

    def policy(self, **options):
        options.setdefault("observation_contract", deepcopy(CONTRACT))
        p = Policy(
            self.path,
            inputs=[fact("Field", "writers", "principal", "agent-a")],
            **options,
        )
        self.addCleanup(p.runtime.close)
        return p

    def test_confirmed_hook_reuses_request_id_and_history_authorizes_only_later_calls(self):
        def after(context, value):
            request = context["request"]
            if request["event"] == "observe":
                p.put("Event", request["id"], request["principal"], request["event"])
                p.put("Field", request["id"], "outcome", "applied")
                p.put("Field", request["id"], "items", 2)
                p.put("Field", request["id"], "observed_at", 1000)
            return value

        p = self.policy(after=after, trace=True)
        invoked = []
        self.assertFalse(
            p.call("agent-a", "consume", {"event": "invented"}, lambda: invoked.append(1))["ok"]
        )
        self.assertEqual(invoked, [])
        self.assertEqual(p.call("agent-a", "observe", {}, lambda: "observed"), "observed")
        event_id = p.events[-1]["id"]
        self.assertEqual(
            p.runtime.query("?- Event(E,P,K).")["rows"],
            [[event_id, "agent-a", "observe"]],
        )
        self.assertEqual(p.call("agent-a", "consume", {"event": event_id}, lambda: "ok"), "ok")
        trace = p.trajectory()
        own_event = fact("Event", event_id, "agent-a", "observe")
        self.assertNotIn(own_event, trace["events"][1]["inputs"])
        self.assertIn(own_event, trace["events"][1]["committedInputs"])
        self.assertIn(own_event, trace["events"][2]["inputs"])
        self.assertFalse(any(f["predicate"] == "Request" for f in p.runtime._inputs))

    def test_event_existence_is_not_a_success_or_permission(self):
        p = self.policy()
        p.put("Event", "failed-call", "agent-a", "observe")
        p.put("Field", "failed-call", "outcome", "not_applied")
        p.put("Field", "failed-call", "observed_at", 1000)
        p.put("Field", "failed-call", "items", 0)
        invoked = []
        self.assertFalse(
            p.call("agent-a", "consume", {"event": "failed-call"}, lambda: invoked.append(1))["ok"]
        )
        self.assertEqual(invoked, [])
        for name in ("Field", "Event"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                FactTool(p, principal="agent-a", predicates=[name])

    def test_declined_and_uncertain_callbacks_do_not_publish_success_facts(self):
        p = self.policy(completed=lambda value: value != "declined", trace=True)

        def decline(context):
            p.put("Event", context["request"]["id"], "agent-a", "observe")
            return "declined"

        self.assertEqual(p.execute("agent-a", "observe", {}, decline), "declined")
        self.assertEqual(p.runtime.query("?- Event(E,P,K).")["rows"], [])

        def uncertain(context):
            p.put("Event", context["request"]["id"], "agent-a", "observe")
            raise RuntimeError("Synthetic unconfirmed external effect.")

        with self.assertRaises(BridgeError) as caught:
            p.execute("agent-a", "observe", {}, uncertain)
        self.assertEqual(caught.exception.code, "execution_uncertain")
        self.assertFalse(any(f["predicate"] == "Event" for f in p.runtime._inputs))
        self.assertEqual([e["outcome"] for e in p.trajectory()["events"]], ["not_applied", "unknown"])

    def test_observation_snapshot_cannot_drop_retained_event(self):
        rows = [
            fact("Field", "writers", "principal", "agent-a"),
            fact("Event", "previous", "agent-a", "observe"),
        ]
        p = Policy(self.path, facts=lambda *_: deepcopy(rows))
        self.addCleanup(p.runtime.close)
        self.assertEqual(p.call("agent-a", "observe", {}, lambda: "ok"), "ok")
        rows.pop()
        invoked = []
        with self.assertRaises(ValueError):
            p.call("agent-a", "observe", {}, lambda: invoked.append(1))
        self.assertEqual(invoked, [])

    def test_checkpoint_retains_event_and_explicit_field_replacement(self):
        checkpoint = self.path.with_name("facts.dl")
        p = self.policy(data=checkpoint)
        p.put("Event", "previous", "agent-a", "observe")
        p.put("Field", "turn-a", "calls", 1)
        p.update(lambda f: (f.delete("Field", "turn-a", "calls", "1"), f.put("Field", "turn-a", "calls", 2)))
        p.runtime.close()
        again = self.policy(data=checkpoint)
        self.assertEqual(again.runtime.query("?- Event(E,P,K).")["rows"], [["previous", "agent-a", "observe"]])
        self.assertEqual(again.runtime.query('?- Field("turn-a","calls",V).')["rows"], [["2"]])
        with self.assertRaises(ValueError):
            again.put("Event", "previous", "other", "observe")
        with self.assertRaises(ValueError):
            again.delete("Event", "previous")

    def test_frozen_call_and_observation_contracts_block_before_business_effects(self):
        p = self.policy(
            observation_contract=deepcopy(CONTRACT),
            call_contract={"observe": {"count": "number", "flag": "boolean", "data": "json"}, "consume": {"event": "symbol"}},
        )
        invoked = []
        for action, parameters in [
            ("unplanned", {}),
            ("observe", {"extra": "value"}),
            ("observe", {"count": "1.5"}),
            ("observe", {"flag": "maybe"}),
            ("observe", {"data": "not JSON"}),
        ]:
            with self.subTest(action=action, parameters=parameters), self.assertRaises(ValueError):
                p.call("agent-a", action, parameters, lambda: invoked.append(1))
        self.assertEqual(invoked, [])
        self.assertEqual(p.call("agent-a", "observe", {"count": 1, "flag": True, "data": []}, lambda: "ok"), "ok")
        p.put("Field", "doc", "owner", "a")
        for name, values in [
            ("Field", ("doc", "owner", "b")),
            ("Field", ("doc", "unknown", "value")),
            ("Field", ("doc", "items", "oops")),
            ("Field", ("doc", "items", 1)),
        ]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                p.put(name, *values)
        self.assertEqual(p.runtime.query('?- Field("doc","owner",O).')["rows"], [["a"]])
