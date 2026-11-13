"""Transactional input-fact edits. The runtime EDB is the only committed authority."""

from copy import deepcopy
import json
from pathlib import Path
import os
from tempfile import NamedTemporaryFile

from policyscope.core.policy import fact, validate_inputs

BUILTIN_KEYS = {"ResourceType": ("Resource",), "ResourceState": ("Resource",)}


class FactUpdates:
    """Private to trusted effect handlers; never expose this object as an agent tool."""

    def __init__(self, binding, rows):
        self._binding, self._rows = binding, deepcopy(rows)
        self._closed = False
        self._fixed = {
            f["predicate"]
            for f in binding.get("configuration", [])
            if self._key(f["predicate"]) is None
        }

    def _key(self, name):
        schema = self._binding["predicates"].get(name, {})
        value = schema.get("key", BUILTIN_KEYS.get(name))
        return None if value is None else tuple(value)

    def _indices(self, name):
        schema = self._binding["predicates"][name]
        key = self._key(name)
        return None if key is None else [schema["args"].index(field) for field in key]

    def rows(self, name):
        if self._closed:
            raise RuntimeError("Fact transaction has ended.")
        if self._binding["predicates"].get(name, {}).get("kind") != "input":
            raise ValueError(
                "Read derived relations through the evaluated context or query."
            )
        return [tuple(row["args"]) for row in self._rows if row["predicate"] == name]

    def put(self, name, *values):
        if self._closed:
            raise RuntimeError("Fact transaction has ended.")
        row = fact(name, *values)
        validate_inputs(self._binding, [row])
        if name in self._fixed:
            raise ValueError("Reviewed configuration is immutable.")
        indices = self._indices(name)
        if indices is not None:
            key = tuple(row["args"][i] for i in indices)
            self._rows = [
                old
                for old in self._rows
                if old["predicate"] != name
                or tuple(old["args"][i] for i in indices) != key
            ]
        if row not in self._rows:
            self._rows.append(row)
        return row

    def delete(self, name, *key):
        if self._closed:
            raise RuntimeError("Fact transaction has ended.")
        schema = self._binding["predicates"].get(name)
        if (
            not schema
            or schema["kind"] != "input"
            or name in self._binding["decision"].values()
            or name in self._fixed
        ):
            raise ValueError("Only mutable non-request inputs may be deleted.")
        indices = self._indices(name)
        if indices is None:
            indices = list(range(len(schema["args"])))
        if len(key) != len(indices):
            raise ValueError("Supply the declared key, or the complete unkeyed row.")
        values = tuple("" if x is None else str(x) for x in key)
        self._rows = [
            row
            for row in self._rows
            if row["predicate"] != name
            or tuple(row["args"][i] for i in indices) != values
        ]

    def _finish(self):
        self._closed = True
        return deepcopy(self._rows)


def load_facts(path, policy_hash):
    source = Path(path).read_text()
    if not source.startswith("// policy-sha256: " + policy_hash + "\n"):
        raise ValueError("Persisted facts belong to a different reviewed policy.")
    import re

    if len(source.encode()) > 1_047_552:
        raise ValueError("Persisted facts exceed the input limit.")
    rows = []
    for line in source.splitlines()[1:]:
        if not line.strip():
            continue
        match = re.fullmatch(r"([A-Za-z][A-Za-z_0-9]*)\((.*)\)\.", line)
        if not match:
            raise ValueError("Persisted EDB may contain only ground input facts.")
        values = json.loads("[" + match[2] + "]")
        if not all(isinstance(value, str) for value in values):
            raise ValueError("Invalid persisted symbol.")
        rows.append(fact(match[1], *values))
    return rows


def save_facts(path, policy_hash, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    source = (
        "// policy-sha256: "
        + policy_hash
        + "\n"
        + "\n".join(
            row["predicate"]
            + "("
            + ", ".join(json.dumps(v, ensure_ascii=False) for v in row["args"])
            + ")."
            for row in rows
        )
        + "\n"
    )
    temporary = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as output:
            temporary = output.name
            output.write(source)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and Path(temporary).exists():
            Path(temporary).unlink()


def lock_facts(path):
    """One writer per persisted scope; all business updates use the runtime queue."""
    import fcntl

    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.with_suffix(path.suffix + ".lock").open("a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        handle.close()
        raise ValueError(
            "This facts file already has an active policy session."
        ) from None
    return handle
