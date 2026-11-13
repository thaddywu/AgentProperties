"""Optional principal-bound, policy-authorized input writes for agent tools."""

from policyscope.core.policy import CORE, fact, text, validate_inputs


class FactTool:
    """Insert/delete only host-allowlisted inputs; Policy.put remains host-only.

    Each request exposes predicate and named fields to Datalog. The original EDB
    authorizes the write; the runtime commits it in the guarded fact transaction.
    Delete requires the complete current tuple, even for keyed inputs.
    """

    def __init__(self, policy, *, principal, predicates):
        if not policy.runtime._managed:
            raise ValueError(
                "Agent fact writes require managed EDB, not an observation-only policy."
            )
        text(principal)
        if not principal.strip() or isinstance(predicates, str):
            raise ValueError("Bind a principal and explicit input predicates.")
        names = tuple(predicates)
        if not names or len(names) != len(set(names)):
            raise ValueError("Choose distinct input predicates.")
        fixed = {
            f["predicate"] for f in policy.runtime.binding.get("configuration", [])
        }
        schemas = policy.runtime.binding["predicates"]
        for name in names:
            schema = schemas.get(name, {})
            if name in CORE or name in fixed or schema.get("kind") != "input":
                raise ValueError("Only mutable, non-request inputs may be exposed.")
            if "predicate" in schema["args"]:
                raise ValueError(
                    "Input field conflicts with the request predicate parameter."
                )
        self.policy, self.principal, self.predicates = (
            policy,
            principal,
            frozenset(names),
        )

    def _write(self, operation, predicate, values):
        if predicate not in self.predicates or not isinstance(values, list):
            raise ValueError("Predicate is not enabled for this connection.")
        if any(not isinstance(value, str) for value in values):
            raise ValueError("Supply string values in declared field order.")
        schema = self.policy.runtime.binding["predicates"][predicate]
        row = fact(predicate, *values)
        validate_inputs(self.policy.runtime.binding, [row])
        parameters = dict(zip(schema["args"], values))
        parameters["predicate"] = predicate

        def commit(_):
            rows = self.policy.rows(predicate)
            target = tuple(values)
            key = schema.get("key")
            indices = [schema["args"].index(field) for field in key] if key else None
            if operation == "put":
                if indices is not None and any(
                    old != target and all(old[i] == target[i] for i in indices)
                    for old in rows
                ):
                    return dict(recorded=False, reason="key_conflict")
                self.policy.put(predicate, *values)
                return dict(recorded=True, changed=target not in rows)
            if target not in rows:
                return dict(recorded=False, reason="row_missing")
            self.policy.delete(
                predicate,
                *([values[i] for i in indices] if indices is not None else values),
            )
            return dict(recorded=True, changed=True)

        return self.policy.execute(self.principal, operation, parameters, commit)

    def put(self, predicate: str, values: list[str]) -> dict:
        """Insert an authorized fact; never overwrite a conflicting keyed record."""
        return self._write("put", predicate, values)

    def delete(self, predicate: str, values: list[str]) -> dict:
        """Delete an authorized complete current fact; cannot erase runtime audit."""
        return self._write("delete", predicate, values)

    def register_mcp(self, server):
        server.tool(name="put")(self.put)
        server.tool(name="delete")(self.delete)

    @property
    def system_card(self):
        shapes = "; ".join(
            name
            + "("
            + ", ".join(self.policy.runtime.binding["predicates"][name]["args"])
            + ")"
            for name in sorted(self.predicates)
        )
        return (
            "Use put/delete only for "
            + shapes
            + ". Supply the predicate and complete values in the field order shown. "
            "The service binds your identity as "
            + self.principal
            + ". Each operation requires policy permission. "
            "put cannot overwrite a different keyed record. delete requires the complete row. "
            "Only refer to operation IDs actually provided for review. "
            "A recorded decision does not itself execute the operation."
        )
