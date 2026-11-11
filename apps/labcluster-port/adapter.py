"""Adaptation code: load one policy scope and interpret original tool events/results."""

from pathlib import Path
from functools import wraps
from policy_runtime import Policy, caller_context


def caller_from_tools(function):
    """Adapt the caller name already held by the original Tools instance."""
    @wraps(function)
    def call(tools, *args, **kwargs):
        with caller_context(tools.role):
            return function(tools, *args, **kwargs)
    return call


def adapt(*, bundle=None):
    return Policy(
        Path(__file__).with_name('rules.dl'), bundle=bundle,
        target='job_id', invariants=('AllocationViolation',),
        event=lambda name, args: 'reject_job' if name == 'approve_job' and args.get('approve') is False else name,
        completed=lambda result: result.get('ok') is not False,
        refused=lambda name: {'status': 'UNAVAILABLE'} if name == 'read_job' else {'ok': False, 'code': 'UNAVAILABLE'},
    )
