"""Private parent/child JSON-lines adapter protocol; never a public network endpoint."""

from contextlib import contextmanager
import json
import select
import sys
import uuid

from .contracts import (Applied, BridgeError, EffectNotAppliedError, NotApplied,
                        ObservationSource, Operation, Snapshot, Unknown)
from .runtime import PolicyRuntime

MAX_FRAME = 1_048_576


def serve():
    runtime = None

    def read():
        line = sys.stdin.buffer.readline(MAX_FRAME + 1)
        if not line:
            raise EOFError("Private adapter pipe closed.")
        if len(line) > MAX_FRAME or not line.endswith(b"\n"):
            raise ValueError("Invalid or oversized adapter frame.")
        message = json.loads(line)
        if not isinstance(message, dict):
            raise ValueError("Expected an adapter message.")
        return message

    def write(message):
        data = json.dumps(message, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode() + b"\n"
        if len(data) > MAX_FRAME:
            raise ValueError("Adapter response exceeds frame limit.")
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()

    def callback(kind, context, name=None):
        identity = str(uuid.uuid4())
        captured = {"policyHash": context["policyHash"], "request": {**context["request"], "parameters": dict(context["request"]["parameters"])}}
        if "derived" in context:
            captured["derived"] = {name: [list(row) for row in rows] for name, rows in context["derived"].items()}
            captured["inputHash"] = context["inputHash"]
            captured["observationVersions"] = dict(context["observationVersions"])
        write({"type": "callback", "id": identity, "kind": kind, "context": captured, "name": name})
        if not select.select([sys.stdin.buffer], [], [], 30)[0]:
            raise TimeoutError("Backend callback did not confirm its outcome.")
        reply = read()
        if reply.get("type") != "callback_result" or reply.get("id") != identity:
            raise ValueError("Unexpected callback response.")
        if reply.get("ok") is not True:
            if reply.get("error", {}).get("code") == "not_applied":
                raise EffectNotAppliedError("Backend certified no effect.")
            raise RuntimeError("Backend callback failed.")
        return reply.get("value")

    @contextmanager
    def transaction(context):
        try:
            callback("begin", context)
            yield
            callback("commit", context)
        except BaseException as error:
            result = callback("rollback", context)
            if isinstance(result, dict) and result.get("notApplied") is True:
                raise EffectNotAppliedError("Backend certified full rollback.") from error
            raise

    def observation(name, context):
        value = callback("observe", context, name)
        return Snapshot(value["version"], value["complete"], value["facts"])

    def effect(name, context):
        value = callback("effect", context, name)
        if value.get("status") == "applied":
            return Applied(value["value"], value.get("observations", []))
        if value.get("status") == "not_applied":
            return NotApplied(value["reason"])
        return Unknown()

    while True:
        try:
            message = read()
        except EOFError:
            return
        identity = message.get("id")
        try:
            if message.get("type") != "request" or not isinstance(identity, str) or not 1 <= len(identity) <= 128:
                raise ValueError("Expected a private adapter request.")
            method, params = message.get("method"), message.get("params", {})
            if method == "configure":
                if runtime is not None:
                    raise ValueError("Worker already configured.")
                sources = [ObservationSource(s["id"], s["predicates"], lambda c, name=s["id"]: observation(name, c)) for s in params.get("observations", [])]
                operations = [Operation(o["action"], lambda c, name=o["action"]: effect(name, c), o.get("observations", []), o.get("reads", [])) for o in params["operations"]]
                runtime = PolicyRuntime(binding=params["binding"], bundle=params["bundle"], inputs=params.get("inputs"), observations=sources, operations=operations, transaction=transaction)
                value = {"policyHash": runtime.policy_hash}
            elif runtime is None:
                raise ValueError("Configure the worker first.")
            elif method == "execute":
                value = runtime.execute(params)
            elif method == "query":
                value = runtime.query(params["source"])
            elif method == "describe_predicates":
                value = runtime.describe_predicates()
            elif method == "check":
                value = runtime.check(params)
            elif method == "snapshot":
                value = runtime.snapshot()
            else:
                raise ValueError("Unknown adapter method.")
            write({"type": "result", "id": identity, "ok": True, "value": value})
        except Exception as error:
            details = {"code": error.code if isinstance(error, BridgeError) else "operation_failed", "message": "Protected operation did not complete."}
            if isinstance(error, BridgeError) and error.attempt_id:
                details["attemptId"] = error.attempt_id
            write({"type": "result", "id": identity, "ok": False, "error": details})
