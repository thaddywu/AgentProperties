"""Awaited native effects preserve loop ownership, facts and cancellation outcomes."""
import asyncio
import inspect
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import threading
import unittest

from policyweave.enforcement import BridgeError, Policy, caller_context, current_caller


RULES = '''Allow(Q) :- Request(Q,P,"check_usage"), Parameter(Q,"pool",P).
Allow(Q) :- Request(Q,P,"stage").
Allow(Q) :- Request(Q,P,"nested").
Allow(Q) :- Request(Q,P,"decline").
'''


@unittest.skipUnless(shutil.which("souffle"), "Native engine required")
class AsyncPolicyTests(unittest.IsolatedAsyncioTestCase):
    def policy(self, **options):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "policy.dl"
        path.write_text(RULES)
        options.setdefault("trace", True)
        options.setdefault("mechanisms", ("observations",))
        return Policy(path, **options)

    async def test_async_decorator_awaits_actual_body_on_original_loop_and_blocks_wrong_pool(self):
        p = self.policy()
        caller_loop, caller_thread = asyncio.get_running_loop(), threading.get_ident()
        calls = []

        @p
        async def check_usage(pool):
            self.assertIs(asyncio.get_running_loop(), caller_loop)
            self.assertEqual(threading.get_ident(), caller_thread)
            self.assertEqual(current_caller(), "reader")
            await asyncio.sleep(0)
            calls.append(pool)
            return {"pool": pool}

        self.assertTrue(inspect.iscoroutinefunction(check_usage))
        with caller_context("reader"):
            self.assertEqual(await check_usage("reader"), {"pool": "reader"})
            self.assertFalse((await check_usage("other"))["ok"])
        self.assertEqual(calls, ["reader"])
        self.assertEqual([e["outcome"] for e in p.trajectory()["events"]], ["applied", "blocked"])

    async def test_staged_facts_and_after_hook_publish_only_after_awaited_success(self):
        started, release = asyncio.Event(), asyncio.Event()
        hooks = []

        def after(context, result):
            hooks.append(threading.get_ident())
            p.put("Field", "receipt", "outcome", "applied")
            return result

        p = self.policy(after=after)

        async def body():
            p.put("Field", "receipt", "value", "pending")
            self.assertIn(("receipt", "value", "pending"), p.rows("Field"))
            started.set()
            await release.wait()
            return {"finished": True}

        task = asyncio.create_task(p.acall("reader", "stage", {}, body))
        await started.wait()
        self.assertFalse(task.done())
        self.assertEqual(hooks, [])
        release.set()
        self.assertEqual(await task, {"finished": True})
        self.assertNotEqual(hooks, [threading.get_ident()])
        fields = {tuple(f["args"]) for f in p.runtime.snapshot()}
        self.assertIn(("receipt", "value", "pending"), fields)
        self.assertIn(("receipt", "outcome", "applied"), fields)

    async def test_exception_after_await_is_unknown_and_does_not_publish_staged_facts(self):
        p = self.policy()
        effects = []

        async def body():
            p.put("Field", "receipt", "value", "staged")
            await asyncio.sleep(0)
            effects.append("external effect may have happened")
            raise RuntimeError("unconfirmed outcome")

        with self.assertRaises(BridgeError) as caught:
            await p.acall("reader", "stage", {}, body)
        self.assertEqual(caught.exception.code, "execution_uncertain")
        self.assertEqual(len(effects), 1)
        self.assertEqual(p.runtime.snapshot(), [])
        self.assertEqual(p.trajectory()["events"][-1]["outcome"], "unknown")
        with self.assertRaises(BridgeError) as caught:
            await p.acall("reader", "stage", {}, body)
        self.assertEqual(caught.exception.code, "session_failed")

    async def test_cancellation_waits_for_cleanup_and_retains_unknown_evidence(self):
        p = self.policy()
        started, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        finished = []

        async def body():
            p.put("Field", "receipt", "value", "staged")
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaning.set()
                await release.wait()
                finished.append(True)

        task = asyncio.create_task(p.acall("reader", "stage", {}, body))
        await started.wait()
        task.cancel()
        await cleaning.wait()
        task.cancel()
        await asyncio.sleep(0)
        self.assertFalse(task.done())
        release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(finished, [True])
        self.assertEqual(p.runtime.snapshot(), [])
        self.assertEqual(p.trajectory()["events"][-1]["outcome"], "unknown")

    async def test_concurrent_calls_are_serialized_without_blocking_the_loop(self):
        p = self.policy()
        started, release = asyncio.Event(), asyncio.Event()
        order = []

        async def first():
            order.append("first-start")
            started.set()
            await release.wait()
            order.append("first-end")
            return "first"

        async def second():
            order.append("second")
            return "second"

        a = asyncio.create_task(p.acall("reader", "stage", {}, first))
        await started.wait()
        b = asyncio.create_task(p.acall("reader", "stage", {}, second))
        await asyncio.sleep(0)
        self.assertEqual(order, ["first-start"])
        release.set()
        self.assertEqual(await asyncio.gather(a, b), ["first", "second"])
        self.assertEqual(order, ["first-start", "first-end", "second"])

    async def test_reentry_fails_without_deadlock_and_declines_do_not_publish(self):
        p = self.policy()

        async def inner():
            return "inner"

        async def outer():
            return await p.acall("reader", "nested", {}, inner)

        with self.assertRaises(BridgeError):
            await asyncio.wait_for(p.acall("reader", "nested", {}, outer), 5)
        self.assertEqual(p.trajectory()["events"][-1]["outcome"], "unknown")

        p = self.policy()

        async def sync_reentry():
            return p.call("reader", "nested", {}, lambda: "inner")

        with self.assertRaises(BridgeError):
            await p.acall("reader", "nested", {}, sync_reentry)
        self.assertEqual(p.trajectory()["events"][-1]["outcome"], "unknown")
        p = self.policy(completed=lambda value: value != "declined")

        async def decline():
            p.put("Field", "receipt", "value", "staged")
            await asyncio.sleep(0)
            return "declined"

        self.assertEqual(await p.acall("reader", "decline", {}, decline), "declined")
        self.assertEqual(p.runtime.snapshot(), [])
        self.assertEqual(p.trajectory()["events"][-1]["outcome"], "not_applied")
