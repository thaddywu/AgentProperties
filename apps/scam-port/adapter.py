"""Adaptation code: configure guards and confirmed bank-result ingestion."""
from pathlib import Path
import time
from policy_runtime import Policy
from tool_adapter import record_result


def adapt(*, now=time.time, inputs=(), bundle=None):
    return Policy(
        Path(__file__).with_name('rules.dl'), inputs=inputs, bundle=bundle,
        before=lambda context: context['facts'].put('Clock', int(now())),
        completed=lambda result: result.get('status') != 'failed',
        after=record_result,
        refused=lambda name: {'status':'denied','reason':'policy'},
    )
