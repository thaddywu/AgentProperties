"""Shared helpers for the Level-A MR families ([`families.py`], [`level_a.py`]).

    suite / fresh_env   load an AgentDojo suite and its default environment
    ad_call             invoke a single tool (used by the oracle-free prechecks)
    agent_exec          run a real LLM agent on a prompt (Level A; needs OPENAI_API_KEY)
    canon               environment -> comparable structure (quotients ids/timestamps)
"""

from __future__ import annotations

import os
from typing import Any

from agentdojo.agent_pipeline.agent_pipeline import AgentPipeline, PipelineConfig
from agentdojo.functions_runtime import FunctionsRuntime
from agentdojo.task_suite.load_suites import get_suite
from agentdojo.task_suite.task_suite import model_output_from_messages

from schema import Execution


def suite(name: str, version: str = "v1"):
    return get_suite(version, name)


def fresh_env(s, task=None):
    """Default environment, initialised for `task` if given."""
    env = s.load_and_inject_default_environment({})
    if task is not None:
        env = task.init_environment(env)
    return env


def ad_call(s, env, fn: str, **kwargs):
    """Invoke a single tool against `env` and return its result."""
    runtime = FunctionsRuntime(s.tools)
    res, err = runtime.run_function(env, fn, kwargs, raise_on_error=False)
    if err:
        raise RuntimeError(f"{fn}: {err}")
    return res


# Wall-clock fields written by tools (datetime.now()); quotiented out of every state comparison.
NONDET = ("timestamp", "last_modified")


def canon(env: Any, drop: tuple[str, ...] = ()) -> Any:
    """Environment -> comparable structure, with `drop` keys (+ timestamps) removed everywhere."""
    data = env.model_dump(mode="json") if hasattr(env, "model_dump") else env
    drop = tuple(drop) + NONDET

    def strip(x):
        if isinstance(x, dict):
            return {k: strip(v) for k, v in x.items() if k not in drop}
        if isinstance(x, list):
            return [strip(v) for v in x]
        return x

    return strip(data)


MODEL = os.environ.get("MR_MODEL", "gpt-4o-mini-2024-07-18")


def agent_exec(suite, prompt: str, env, label: str = "") -> Execution:
    """Level A: run the agent to completion on `prompt` against `env`; return the observation tuple.

    Needs OPENAI_API_KEY. Each call is a fresh single-shot pipeline (no conversation memory);
    the environment is mutated in place and also returned as `s_post`.
    """
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
