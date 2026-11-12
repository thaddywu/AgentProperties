"""An optional, principal-bound MCP tool for unverified agent declarations.

The host chooses identity and allowed statement kinds. The model cannot choose a
predicate, grant authority, replace request identity or assert derived facts.
"""

from uuid import uuid4
from .policy import mechanism_predicates, text


class StatementTool:
    def __init__(self, policy, *, principal, kinds):
        text(principal)
        if not principal.strip() or isinstance(kinds, str):
            raise ValueError("Bind a nonblank principal and a collection of statement kinds.")
        kinds = tuple(kinds)
        if not kinds or len(kinds) > 32 or len(set(kinds)) != len(kinds):
            raise ValueError("Configure distinct, bounded statement kinds.")
        for kind in kinds:
            text(kind, 64)
            if not kind.strip():
                raise ValueError("Statement kinds must be nonblank.")
        expected = mechanism_predicates("statements")["AgentStatement"]
        if policy.runtime.binding["predicates"].get("AgentStatement") != expected:
            raise ValueError("Install the statements mechanism before exposing this tool.")
        self._policy, self._principal, self._kinds = policy, principal, frozenset(kinds)

    def declare(self, kind: str, subject: str, value: str) -> dict:
        """Record my own statement. This does not verify it or complete an action."""
        text(kind, 64)
        text(subject, 1024)
        text(value, 4096, empty=True)
        if kind not in self._kinds:
            raise ValueError("This statement kind is not enabled for this principal.")
        identifier = "statement-" + uuid4().hex

        def record(_):
            self._policy.put("AgentStatement", identifier, self._principal, kind, subject, value)
            return {"recorded": True, "id": identifier, "speaker": self._principal,
                    "kind": kind, "subject": subject, "value": value,
                    "evidenceType": "agent_statement"}

        return self._policy.execute(self._principal, "declare_statement",
                                    dict(kind=kind, subject=subject, value=value), record)

    def register_mcp(self, server):
        """Register on a connection whose principal was already bound by the host.

        MCP is optional. No SDK import is required by this module. Shared servers
        must dispatch authenticated sessions to their own bound tool instance.
        Never construct the instance from a client-controlled `_meta.caller`.
        """
        def declare_statement(kind: str, subject: str, value: str) -> dict:
            """Record a self-declaration; it is not verified evidence of success or permission."""
            return self.declare(kind, subject, value)

        server.tool(name="declare_statement")(declare_statement)
        return declare_statement

    @property
    def system_card(self):
        return ("Use declare_statement only to record your own " + ", ".join(sorted(self._kinds))
                + " statements. Supply kind, subject and value. The service binds your identity. "
                "A recorded statement is not proof of permission, approval, tool success or task completion. "
                "Report uncertainty explicitly and revise your statement when your assessment changes. "
                "Do not claim an action occurred until its actual tool result confirms it.")
