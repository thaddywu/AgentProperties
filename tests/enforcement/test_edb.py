"""The managed EDB boundary: keys, atomic updates, lifecycle and persistence."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from policyscope.enforcement import Policy, BridgeError, caller_context, current_caller

SOURCE = """.decl Grant(Principal:symbol, Resource:symbol)
.input Grant
.key Grant(Principal)
Grant("reader", "a").
.decl Counter(Value:number)
.input Counter
.key Counter()
Counter(0).
Allow(Q) :- Request(Q, P, "read"), Parameter(Q, "resource", R), Grant(P, R).
Seen(R) :- Grant(P, R).
""".replace("Seen(R) :-", ".decl Seen(Resource:symbol)\nSeen(R) :-")


class ManagedEDB(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "rules.dl"
        self.path.write_text(SOURCE)

    def policy(self, **options):
        p = Policy(self.path, local_effects=True, **options)
        self.addCleanup(p.runtime.close)
        return p

    def test_keyed_and_singleton_updates_replace_old_inputs_and_derived_rows(self):
        p = self.policy()

        def change(context):
            context["facts"].put("Grant", "reader", "b")
            context["facts"].put("Counter", 1)
            return "body"

        self.assertEqual(p.execute("reader", "read", {"resource": "a"}, change), "body")
        self.assertEqual(p.runtime.query("?- Seen(R).")["rows"], [["b"]])
        self.assertEqual(p.runtime.query("?- Counter(N).")["rows"], [["1"]])
        self.assertEqual(
            p.call("reader", "read", {"resource": "a"}, lambda: "wrong"),
            {"ok": False, "code": "UNAVAILABLE"},
        )

    def test_failed_local_edits_are_not_published_and_handles_expire(self):
        p = self.policy()
        handles = []

        def fail(context):
            handles.append(context["facts"])
            context["facts"].put("Counter", 9)
            raise RuntimeError("synthetic")

        with self.assertRaises(BridgeError):
            p.execute("reader", "read", {"resource": "a"}, fail)
        self.assertEqual(p.runtime.query("?- Counter(N).")["rows"], [["0"]])
        with self.assertRaises(RuntimeError):
            handles[0].put("Counter", 10)
        self.assertEqual(
            p.call("reader", "read", {"resource": "a"}, lambda: "ok"), "ok"
        )

    def test_direct_facade_joins_wrap_call_and_execute_without_early_publication(self):
        p = self.policy(completed=lambda value: value != "refused")
        p.put("Counter", 2)  # Trusted host ingestion outside a tool.
        self.assertEqual(p.runtime.query("?- Counter(N).")["rows"], [["2"]])

        def change(event):
            p.put("Counter", 3)
            self.assertEqual(p.rows("Counter"), [("3",)])
            self.assertIn({"predicate": "Counter", "args": ["2"]}, p.runtime._inputs)
            return event

        self.assertEqual(
            p.wrap("reader", "read", {"resource": "a"}, change)("original-event"),
            "original-event",
        )
        self.assertEqual(p.runtime.query("?- Counter(N).")["rows"], [["3"]])
        denied = []
        p.call(
            "other",
            "read",
            {"resource": "a"},
            lambda: denied.append(p.put("Counter", 99)),
        )
        self.assertEqual(denied, [])
        self.assertEqual(
            p.call(
                "reader",
                "read",
                {"resource": "a"},
                lambda: (p.put("Counter", 4), "refused")[1],
            ),
            "refused",
        )
        self.assertEqual(p.runtime.query("?- Counter(N).")["rows"], [["3"]])

        def fail(context):
            p.put("Counter", 5)
            p.delete("Grant", "reader")
            raise RuntimeError("synthetic failure")

        with self.assertRaises(BridgeError):
            p.execute("reader", "read", {"resource": "a"}, fail)
        self.assertEqual(p.runtime.query("?- Counter(N).")["rows"], [["3"]])
        with self.assertRaises(RuntimeError):
            p.rows("Counter")
        p.put("Counter", 6)  # The ended callback context was reset, even after failure.
        self.assertEqual(p.runtime.query("?- Counter(N).")["rows"], [["6"]])

    def test_direct_facade_does_not_share_a_batch_with_an_unrelated_thread(self):
        import threading

        p = self.policy()
        started = threading.Event()
        finished = threading.Event()
        errors = []

        def host_update():
            started.set()
            try:
                p.put("Counter", 8)
            except BaseException as error:
                errors.append(error)
            finally:
                finished.set()

        thread = threading.Thread(target=host_update)

        def change(context):
            p.put("Counter", 7)
            thread.start()
            self.assertTrue(started.wait(2))
            self.assertFalse(finished.is_set())
            self.assertEqual(p.rows("Counter"), [("7",)])
            return "done"

        try:
            p.execute("reader", "read", {"resource": "a"}, change)
        finally:
            if thread.ident is not None:
                thread.join(5)
        self.assertTrue(finished.is_set())
        self.assertEqual(errors, [])
        self.assertEqual(p.runtime.query("?- Counter(N).")["rows"], [["8"]])

    def test_tool_decorator_reads_caller_at_invocation_and_stages_updates(self):
        p = self.policy()
        seen = []

        @p
        def read(resource, principal="body-argument"):
            seen.append(current_caller())
            p.put("Counter", 1)
            return resource

        with self.assertRaises(RuntimeError):
            read("a")
        self.assertEqual(seen, [])
        with caller_context("reader"):
            self.assertEqual(read("a", principal="not-the-caller"), "a")
            with caller_context("other"):
                self.assertFalse(read("a")["ok"])
            self.assertEqual(current_caller(), "reader")
        with self.assertRaises(RuntimeError):
            current_caller()
        self.assertEqual(seen, ["reader"])
        self.assertEqual(
            [event["principal"] for event in p.events], ["reader", "other"]
        )
        self.assertEqual(p.runtime.query("?- Counter(N).")["rows"], [["1"]])

        @p(name="read", arguments={"resource": "a"})
        def callback(event_id):
            return event_id

        with caller_context("reader"):
            self.assertEqual(callback("trace-event"), "trace-event")
        self.assertEqual(p.events[-1]["upstreamEvent"], "trace-event")

    def test_caller_context_isolated_between_async_tasks_and_reset_on_error(self):
        import asyncio

        async def task(name):
            with caller_context(name):
                await asyncio.sleep(0)
                return current_caller()

        async def collect():
            return await asyncio.gather(task("first"), task("second"))

        self.assertEqual(asyncio.run(collect()), ["first", "second"])
        with self.assertRaises(RuntimeError):
            current_caller()
        with self.assertRaises(ValueError):
            with caller_context(""):
                self.fail("Blank caller was accepted.")
        with self.assertRaisesRegex(RuntimeError, "synthetic"):
            with caller_context("reader"):
                raise RuntimeError("synthetic")
        with self.assertRaises(RuntimeError):
            current_caller()

    def test_request_and_derived_facts_cannot_be_inserted(self):
        p = self.policy()
        for predicate, values in [
            ("Request", ("forged", "reader", "read")),
            ("Allow", ("forged",)),
            ("Seen", ("a",)),
        ]:
            with self.assertRaises(ValueError):
                p.put(predicate, *values)

    def test_delete_handles_keys_singletons_and_complete_unkeyed_tuples(self):
        self.path.write_text(SOURCE + "\n.decl Note(Value:symbol)\n.input Note\n")
        p = self.policy()
        p.put("Note", "a")
        p.put("Note", "a")
        p.put("Note", "b")
        self.assertEqual(sorted(p.runtime.query("?- Note(V).")["rows"]), [["a"], ["b"]])
        p.delete("Note", "a")
        self.assertEqual(p.runtime.query("?- Note(V).")["rows"], [["b"]])
        p.delete("Counter")
        self.assertEqual(p.runtime.query("?- Counter(N).")["rows"], [])

        def remove(context):
            p.delete("Grant", "reader")
            self.assertEqual(p.rows("Grant"), [])
            self.assertIn(
                {"predicate": "Grant", "args": ["reader", "a"]}, p.runtime._inputs
            )
            return "done"

        self.assertEqual(p.execute("reader", "read", {"resource": "a"}, remove), "done")
        self.assertEqual(p.runtime.query("?- Seen(R).")["rows"], [])
        for name, values in [
            ("Allow", ("forged",)),
            ("Request", ("forged",)),
            ("Note", ()),
        ]:
            with self.assertRaises(ValueError):
                p.delete(name, *values)

    def test_checkpoint_does_not_resurrect_deleted_seed_and_has_one_writer(self):
        checkpoint = self.path.with_name("facts.dl")
        p = self.policy(data=checkpoint)
        p.delete("Grant", "reader")
        with self.assertRaises(ValueError):
            Policy(self.path, data=checkpoint)
        p.runtime.close()
        again = self.policy(data=checkpoint)
        self.assertEqual(again.runtime.query("?- Grant(P, R).")["rows"], [])

    def test_fsm_changes_state_only_after_confirmed_effect(self):
        self.path.write_text("""AllowedTransition("artifact", "approve", "draft", "approved").
ResourceType("a", "artifact").
ResourceState("a", "draft").
Allow(Q) :- Request(Q, P, "approve"), Parameter(Q, "resource", "a"), CanTransition("a", "approve", "draft", "approved").""")
        p = self.policy()

        def approve(context):
            self.assertIs(p.transition, context["transition"])
            with self.assertRaises(TypeError):
                p.transition["to"] = "forged"
            return "done"

        self.assertEqual(
            p.execute("reviewer", "approve", {"resource": "a"}, approve), "done"
        )
        self.assertEqual(
            p.runtime.query("?- ResourceState(R, S).")["rows"], [["a", "approved"]]
        )
        self.assertEqual(p.runtime.query("?- CanTransition(R, E, F, T).")["rows"], [])

    def test_direct_resource_puts_check_initial_state_and_never_reset_existing_state(
        self,
    ):
        self.path.write_text("""InitialState("artifact", "draft").
AllowedTransition("artifact", "publish", "draft", "published").
Allow(Q) :- Request(Q, P, "create").
Allow(Q) :- Request(Q, P, "publish"), Parameter(Q, "resource", R), CanTransition(R, "publish", "draft", "published").""")
        p = self.policy()

        def create(policy, identity, kind, state):
            policy.put("ResourceType", identity, kind)
            policy.put("ResourceState", identity, state)
            return state

        self.assertEqual(
            p.call("owner", "create", {}, lambda: create(p, "a", "artifact", "draft")),
            "draft",
        )
        p.call("owner", "publish", {"resource": "a"}, lambda: "done")
        for identity, kind, state in [
            ("a", "artifact", "draft"),
            ("b", "unknown", "draft"),
            ("c", "artifact", "published"),
        ]:
            with self.assertRaises(BridgeError):
                p.call("owner", "create", {}, lambda: create(p, identity, kind, state))
        with self.assertRaises(BridgeError):
            p.call(
                "owner",
                "create",
                {},
                lambda: p.put("ResourceType", "missing-state", "artifact"),
            )
        self.assertEqual(
            p.runtime.query("?- ResourceState(R, S).")["rows"], [["a", "published"]]
        )
        self.path.write_text(
            'InitialState("artifact", "draft").\nAllow(Q) :- Request(Q, P, "create").'
        )
        initial_only = self.policy()
        self.assertEqual(
            initial_only.call(
                "owner",
                "create",
                {},
                lambda: create(initial_only, "b", "artifact", "draft"),
            ),
            "draft",
        )
        self.path.write_text(
            'InitialState("artifact", "draft").\nInitialState("artifact", "other").\nAllow(Q) :- Request(Q, P, "create").'
        )
        with self.assertRaisesRegex(ValueError, "initial state"):
            Policy(self.path)
        self.path.write_text(
            'AllowedTransition("artifact", "publish", "draft", "published").\nAllow(Q) :- Request(Q, P, "publish").'
        )
        observed = Policy(
            self.path,
            facts=lambda context, data: [
                {"predicate": "ResourceType", "args": ["c", "artifact"]},
                {"predicate": "ResourceState", "args": ["c", "draft"]},
            ],
        )
        self.addCleanup(observed.runtime.close)
        intent = {
            "actor": "owner",
            "action": "publish",
            "parameters": {"resource": "c"},
        }
        self.assertTrue(observed.runtime.capture(intent).check(intent)["allowed"])


if __name__ == "__main__":
    unittest.main()
