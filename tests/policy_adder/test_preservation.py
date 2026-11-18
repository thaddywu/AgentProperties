from pathlib import Path
import tempfile
import unittest

from policyweave.policy_adder.preservation import instrumentation_errors


class PreservationTests(unittest.TestCase):
    def test_policy_hook_preserves_original_body_but_guard_and_effect_rewrites_fail(
        self,
    ):
        original = """def transfer(owner, amount):
    if owner != "self":
        raise ValueError("ownership")
    if amount > 10:
        raise ValueError("limit")
    return ledger.send(amount)
"""
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / "original.py", Path(directory) / "candidate.py"
            a.write_text(original)
            b.write_text("from policy_port import policy\n@policy\n" + original)
            self.assertEqual(instrumentation_errors(a, b), [])
            for changed in [
                original.replace("amount > 10", "amount > 20"),
                original.replace("return ledger.send(amount)", 'return {"ok": True}'),
                original.replace(
                    "    return ledger.send(amount)",
                    "    ledger.notify(amount)\n    return ledger.send(amount)",
                ),
                original.replace(
                    '    if owner != "self":\n        raise ValueError("ownership")\n',
                    "",
                ),
            ]:
                b.write_text(changed)
                self.assertTrue(instrumentation_errors(a, b))

    def test_existing_callback_can_be_wrapped_without_replacing_the_business_body(self):
        original = "def call(actor, fn):\n    return fn()\n"
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / "original.py", Path(directory) / "candidate.py"
            a.write_text(original)
            b.write_text(
                "from policy_port import policy\ndef call(actor, fn):\n    fn = policy.wrap(actor, fn)\n    return fn()\n"
            )
            self.assertEqual(instrumentation_errors(a, b), [])
            b.write_text(
                "from policy_port import policy\ndef call(actor, fn):\n    fn = policy.fake_success()\n    return fn()\n"
            )
            self.assertTrue(instrumentation_errors(a, b))
