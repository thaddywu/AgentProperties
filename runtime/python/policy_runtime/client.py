"""Standard-library-only, synchronous integration over a private subprocess pipe.

The caller owns authentication, storage, source completeness and transaction semantics.
No model output may configure sources, operations or identity.
"""

from contextlib import AbstractContextManager
from copy import deepcopy
from dataclasses import asdict
import json
import subprocess
import sys
import threading
from typing import Callable, Sequence
import uuid

MAX_LINE = 1_048_576
from .contracts import (Applied, BridgeError, Context, EffectNotAppliedError, Fact,
                        NotApplied, ObservationSource, Operation, Snapshot, Unknown)


class _BoundPort:
    def __init__(self, client: "PolicyClient", principal: str):
        self._client, self._principal = client, principal

    def execute(self, action: str, resource: str | None = None, parameters: dict[str, str] | None = None):
        try:
            result = self._client._exchange("execute", {
                "actor": self._principal, "action": action,
                **({"resource": resource} if resource is not None else {}),
                "parameters": parameters or {},
            })
        except BridgeError as error:
            raise BridgeError(error.code, "Protected operation did not complete.", error.attempt_id) from None
        public = {"allowed": result["allowed"], "attemptId": result["decision"]["request"]["id"]}
        if result["allowed"]:
            public["value"] = result["value"]
        return public


class PolicyClient:
    def __init__(
        self, command: Sequence[str] | None = None, *, binding: dict, bundle: dict,
        observations: Sequence[ObservationSource], operations: Sequence[Operation],
        inputs: list[Fact] | None = None,
        transaction: Callable[[Context], AbstractContextManager] | None = None,
    ):
        self._sources = {source.id: source for source in observations}
        self._operations = {operation.action: operation for operation in operations}
        if len(self._sources) != len(observations) or len(self._operations) != len(operations):
            raise ValueError("Sources and operations must have distinct names.")
        self._transaction_factory = transaction
        self._transaction: AbstractContextManager | None = None
        self._lock = threading.Lock()
        self._active_thread: int | None = None
        self._process = subprocess.Popen(
            list(command) if command is not None else [sys.executable, "-m", "policy_runtime", "serve"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, encoding="utf-8", bufsize=1,
        )
        try:
            result = self._exchange("configure", {
                "binding": binding, "bundle": bundle,
                **({"inputs": inputs} if inputs is not None else {}),
                "observations": [{"id": s.id, "predicates": list(s.predicates)} for s in observations],
                "operations": [{"action": o.action, "observations": list(o.observations), "reads": list(o.reads)} for o in operations],
            })
            self.policy_hash = result["policyHash"]
        except BaseException:
            self.close()
            raise

    def bind(self, authenticated_principal: str):
        return _BoundPort(self, authenticated_principal)

    def query(self, source: str):
        return self._exchange("query", {"source": source})

    def describe_predicates(self):
        return self._exchange("describe_predicates", {})

    def _send(self, message):
        line = json.dumps(message, ensure_ascii=True, allow_nan=False)
        if len(line) > MAX_LINE:
            raise BridgeError("protocol_error", "Bridge message exceeds the size limit.")
        try:
            self._process.stdin.write(line + "\n")
            self._process.stdin.flush()
        except (OSError, ValueError) as error:
            raise BridgeError("transport_closed", "Policy pipe closed; execution outcome is unknown.") from error

    def _callback(self, message):
        context, kind = message["context"], message["kind"]
        if kind == "begin":
            if self._transaction is not None:
                raise RuntimeError("A backend transaction is already active.")
            if self._transaction_factory:
                manager = self._transaction_factory(context)
                manager.__enter__()
                self._transaction = manager
            return None
        if kind == "commit":
            manager, self._transaction = self._transaction, None
            if manager is not None:
                manager.__exit__(None, None, None)
            return None
        if kind == "rollback":
            manager, self._transaction = self._transaction, None
            if manager is not None:
                error = RuntimeError("Policy operation aborted; roll back all managed effects.")
                try:
                    manager.__exit__(type(error), error, None)
                except EffectNotAppliedError:
                    return {"notApplied": True}
            return {"notApplied": False}
        if kind == "observe":
            snapshot = self._sources[message["name"]].read(context)
            if not isinstance(snapshot, Snapshot):
                raise TypeError("An observation must return a Snapshot.")
            return asdict(snapshot)
        if kind == "effect":
            outcome = self._operations[message["name"]].execute(context)
            if not isinstance(outcome, (Applied, NotApplied, Unknown)):
                raise TypeError("An operation must explicitly report Applied, NotApplied or Unknown.")
            return asdict(outcome)
        raise ValueError("Unknown backend callback.")

    def _exchange(self, method, params):
        if self._active_thread == threading.get_ident():
            raise BridgeError("reentrant_call", "A callback cannot call its own policy session.")
        params = deepcopy(params)
        with self._lock:
            self._active_thread = threading.get_ident()
            try:
                request_id = uuid.uuid4().hex
                callback_error = None
                self._send({"type": "request", "id": request_id, "method": method, "params": params})
                while True:
                    line = self._process.stdout.readline(MAX_LINE + 1)
                    if not line or len(line) > MAX_LINE or not line.endswith("\n"):
                        raise BridgeError("transport_closed", "Policy pipe closed; execution outcome is unknown.")
                    message = json.loads(line)
                    if message.get("type") == "callback":
                        try:
                            value = self._callback(message)
                            # Serialization failure after an effect is also an uncertain result.
                            json.dumps(value, allow_nan=False)
                            reply = {"type": "callback_result", "id": message["id"], "ok": True, "value": value}
                        except Exception as error:
                            callback_error = error
                            code = "not_applied" if isinstance(error, EffectNotAppliedError) else "callback_failed"
                            reply = {"type": "callback_result", "id": message["id"], "ok": False, "error": {"code": code}}
                        try:
                            self._send(reply)
                        except (TypeError, ValueError, BridgeError):
                            self._send({"type": "callback_result", "id": message["id"], "ok": False, "error": {"code": "callback_failed"}})
                        continue
                    if message.get("type") != "result" or message.get("id") != request_id:
                        raise BridgeError("protocol_error", "Unexpected policy pipe response.")
                    if message.get("ok") is not True:
                        error = message["error"]
                        raise BridgeError(error["code"], error["message"], error.get("attemptId")) from callback_error
                    return message.get("value")
            finally:
                self._active_thread = None

    def close(self):
        if self._process.stdin:
            self._process.stdin.close()
        try:
            self._process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait()
        if self._process.stdout:
            self._process.stdout.close()
        # Pipe loss is not confirmation that an external effect was rolled back.
        if self._transaction is not None:
            manager, self._transaction = self._transaction, None
            error = RuntimeError("Policy pipe closed during a backend transaction.")
            try:
                manager.__exit__(type(error), error, None)
            except EffectNotAppliedError:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
