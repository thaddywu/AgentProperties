"""One LLM episode: system prompt + tools + a dispatch function. Application-agnostic.

This is the `/v1/responses` tool-calling loop that every application uses to drive its
acting agent. It knows nothing about any application: the caller supplies the tool
schemas, a `dispatch(name, args) -> dict`, and a `stop(name, args, out) -> bool` that says
which call ends the episode (usually "the agent delivered its final artefact").

    OPENAI_API_KEY=dummy OPENAI_BASE_URL=http://127.0.0.1:18080/v1

`applications/opsdesk/agent.py` is the frozen ancestor of this file and deliberately still
carries its own copy: every OpsDesk sweep in `results/` was produced by it, and rewriting
it in terms of this module would silently re-parent a frozen result.
"""
import json
import os

DEFAULT_MODEL = "gpt-5.6-sol"


def client():
    from openai import OpenAI
    key = os.environ.get("OPENAI_API_KEY") or "dummy"
    return OpenAI(api_key=key)


def run_episode(system, tools, dispatch, opening, model=DEFAULT_MODEL, max_steps=25,
                stop=None, trace_items=None):
    """Drive one episode. Returns (n_steps, stopped_cleanly)."""
    cl = client()
    schema = [{"type": "function", "name": t["name"], "description": t["description"],
               "parameters": t["input_schema"]} for t in tools]
    items = [{"role": "user", "content": opening}]

    for step in range(max_steps):
        r = cl.responses.create(model=model, instructions=system, input=items, tools=schema)
        items += [o.model_dump(exclude_none=True) for o in r.output]
        calls = [o for o in r.output if o.type == "function_call"]
        if not calls:
            if trace_items is not None:
                trace_items.extend(items)
            return step, False
        done = False
        for c in calls:
            args = json.loads(c.arguments or "{}")
            try:
                out = dispatch(c.name, args)
            except Exception as e:                       # a malformed call is the agent's
                out = {"error": f"bad_call: {e}"}        # problem, not the harness's
            items.append({"type": "function_call_output", "call_id": c.call_id,
                          "output": json.dumps(out)[:6000]})
            if stop and stop(c.name, args, out):
                done = True
        if done:
            break
    if trace_items is not None:
        trace_items.extend(items)
    return step, True
