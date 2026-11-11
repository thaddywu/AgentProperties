"""Offline cross-language conformance; all identities and state are fictional."""

from contextlib import contextmanager, nullcontext
import json
from pathlib import Path
import sqlite3
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from policy_runtime import Applied, BridgeError, EffectNotAppliedError, NotApplied, ObservationSource, Operation, PolicyClient, PolicyRuntime, Snapshot, Unknown

CONFIG = json.loads(Path(sys.argv.pop(1)).read_text())
COMMAND = json.loads(sys.argv.pop(1))


def fact(predicate, *args):
    return {"predicate": predicate, "args": list(args)}


class Conformance(unittest.TestCase):
    def client(self, effect, source=None, transaction=None):
        factory = (lambda **kwargs: PolicyRuntime(**kwargs)) if COMMAND == ["native"] else (lambda **kwargs: PolicyClient(COMMAND, **kwargs))
        return factory(**CONFIG,
            observations=[ObservationSource("registry", ("Grant", "Version"), source or (lambda _: Snapshot("v1", True, [fact("Grant", "operator", "item"), fact("Version", "item", "v1")])))],
            operations=[Operation("apply", effect, ("Done",))], transaction=transaction)

    def test_denial_revocation_and_result_receipts(self):
        grants = [fact("Grant", "operator", "item")]
        effects = []
        def apply(context):
            effects.append(dict(context["request"]))
            return Applied("changed", [fact("Done", context["request"]["id"], "receipt")])
        with self.client(apply, lambda _: Snapshot("v1", True, grants + [fact("Version", "item", "v1")])) as client:
            actor = client.bind("operator")
            self.assertFalse(actor.execute("apply", "item", {"version": "v2"})["allowed"])
            self.assertFalse(client.bind("other").execute("apply", "item", {"version": "v1"})["allowed"])
            result = actor.execute("apply", "item", {"version": "v1"})
            self.assertEqual(result["value"], "changed")
            self.assertEqual(client.query("?- Done(Q, R).")["rows"], [[result["attemptId"], "receipt"]])
            self.assertEqual(set(result), {"allowed", "attemptId", "value"})
            grants.clear()
            self.assertFalse(actor.execute("apply", "item", {"version": "v1"})["allowed"])
            self.assertEqual(len(effects), 1)

    def test_explicit_failure_and_unknown_result_are_distinct(self):
        mode = [NotApplied("business_refusal")]
        with self.client(lambda _: mode[0]) as client:
            with self.assertRaises(BridgeError) as refused:
                client.bind("operator").execute("apply", "item", {"version": "v1"})
            self.assertEqual(refused.exception.code, "not_applied")
            mode[0] = Unknown()
            with self.assertRaises(BridgeError) as uncertain:
                client.bind("operator").execute("apply", "item", {"version": "v1"})
            attempt = uncertain.exception.attempt_id
            self.assertEqual(uncertain.exception.code, "execution_uncertain")
            with self.assertRaises(BridgeError):
                client.bind("operator").execute("apply", "item", {"version": "v1"})

    def test_sqlite_rollback_is_certified_and_queued_snapshots_are_current(self):
        db = sqlite3.connect(":memory:", isolation_level=None, check_same_thread=False)
        self.addCleanup(db.close)
        db.execute("CREATE TABLE registry (version TEXT)")
        db.execute("INSERT INTO registry VALUES ('v1')")
        order = []
        @contextmanager
        def transaction(_):
            db.execute("BEGIN IMMEDIATE")
            order.append("begin")
            try:
                yield
                db.commit()
                order.append("commit")
            except Exception as error:
                db.rollback()
                order.append("rollback")
                raise EffectNotAppliedError("Confirmed SQLite rollback.") from error
        def source(_):
            version = db.execute("SELECT version FROM registry").fetchone()[0]
            return Snapshot(version, True, [fact("Grant", "operator", "item"), fact("Version", "item", version)])
        fail = [True]
        def effect(_):
            db.execute("UPDATE registry SET version='v2'")
            if fail[0]:
                raise RuntimeError("fault after local write")
            return Applied("updated")
        with self.client(effect, source, transaction) as client:
            actor = client.bind("operator")
            with self.assertRaises(BridgeError) as rollback:
                actor.execute("apply", "item", {"version": "v1"})
            self.assertEqual(rollback.exception.code, "not_applied")
            self.assertEqual(db.execute("SELECT version FROM registry").fetchone()[0], "v1")
            fail[0] = False
            results = []
            threads = [threading.Thread(target=lambda: results.append(actor.execute("apply", "item", {"version": "v1"})["allowed"])) for _ in range(2)]
            for thread in threads: thread.start()
            for thread in threads: thread.join(timeout=5)
            self.assertEqual(sorted(results), [False, True])
            self.assertEqual(order, ["begin", "rollback", "begin", "commit", "begin", "commit"])

    def test_invalid_source_and_untyped_business_result_fail_closed(self):
        calls = []
        with self.client(lambda _: calls.append(1), lambda _: Snapshot("v1", False, [])) as client:
            with self.assertRaises(BridgeError):
                client.bind("operator").execute("apply", "item", {"version": "v1"})
        self.assertEqual(calls, [])
        with self.client(lambda _: {"ok": False}) as client:
            with self.assertRaises(BridgeError) as invalid:
                client.bind("operator").execute("apply", "item", {"version": "v1"})
            self.assertEqual(invalid.exception.code, "execution_uncertain")
            self.assertEqual(client.query("?- Done(Q, R).")["rows"], [])

    def test_oversized_effect_result_stops_before_success_commit(self):
        with self.client(lambda _: Applied("x" * 600_000)) as client:
            with self.assertRaises(BridgeError) as large:
                client.bind("operator").execute("apply", "item", {"version": "v1"})
            self.assertEqual(large.exception.code, "execution_uncertain")
            self.assertEqual(client.query("?- Done(Q, R).")["rows"], [])

    def test_context_manager_exit_does_not_by_itself_certify_rollback(self):
        effects = []
        def effect(_):
            effects.append("external_effect")
            return Unknown()
        with self.client(effect, transaction=lambda _: nullcontext()) as client:
            with self.assertRaises(BridgeError) as uncertain:
                client.bind("operator").execute("apply", "item", {"version": "v1"})
            self.assertEqual(uncertain.exception.code, "execution_uncertain")
        self.assertEqual(effects, ["external_effect"])


if __name__ == "__main__":
    unittest.main()
