"""Small actual in-memory backend for exercising the study workflow, not research evidence."""

from copy import deepcopy
from time import perf_counter_ns

from policyscope.enforcement import (
    Applied,
    ObservationSource,
    Operation,
    PolicyRuntime,
    Snapshot,
    compile_policy,
    fact,
)
from policyscope.core.policy import CORE, fingerprint, read_binding
from policyscope.analysis import QuerySession


class Application:
    name = "Document access · example"
    revision = "document-access-example-v1"
    policy_origin = "developer-reference"
    policy = "Only the owner may read a document.\n\nArchived documents cannot be read."
    source = """Allow(Q) :- Request(Q, A, "read"), Parameter(Q, "document", D), Owner(D, A).
Deny(Q, "archived") :- Request(Q, A, "read"), Parameter(Q, "document", D), Archived(D)."""

    def __init__(self):
        predicates = deepcopy(CORE)
        predicates.update(
            Owner=dict(
                kind="input",
                args=["Document", "Actor"],
                meaning="Document owner read from the application store.",
            ),
            Archived=dict(
                kind="input",
                args=["Document"],
                meaning="The application store marks this document archived.",
            ),
        )
        self.binding = read_binding(
            dict(
                version=1,
                id="document-access-example",
                context="A scripted in-memory document backend. Actor comes from the experiment's authenticated test identity. The document request parameter selects a stored document.",
                predicates=predicates,
                decision=dict(
                    request="Request",
                    allow="Allow",
                    deny="Deny",
                    parameters="Parameter",
                ),
                tests=[
                    dict(
                        name="owner",
                        inputs=[fact("Owner", "doc-a", "alice")],
                        request=dict(
                            actor="alice",
                            action="read",
                            parameters={"document": "doc-a"},
                        ),
                        allowed=True,
                    ),
                    dict(
                        name="other owner",
                        inputs=[fact("Owner", "doc-a", "alice")],
                        request=dict(
                            actor="bob", action="read", parameters={"document": "doc-a"}
                        ),
                        allowed=False,
                    ),
                    dict(
                        name="archived",
                        inputs=[
                            fact("Owner", "doc-a", "alice"),
                            fact("Archived", "doc-a"),
                        ],
                        request=dict(
                            actor="alice",
                            action="read",
                            parameters={"document": "doc-a"},
                        ),
                        allowed=False,
                    ),
                ],
            )
        )
        # Lazy compile: reviewing text works without a native engine; running needs Soufflé.
        self._bundle = None
        from policyscope.core.policy import installed_rules

        self.policy_hash = fingerprint(
            dict(
                version=2,
                binding=self.binding,
                source=self.source,
                rules=installed_rules(self.binding, self.source),
            )
        )
        self.documents = []
        self.setup_fields = [
            dict(name="actor", label="Reader", options=["alice", "bob"]),
            dict(name="document", label="Document", options=["doc-a", "doc-b"]),
            dict(name="state", label="State", options=["active", "archived"]),
        ]

    def reference(self):
        statements = [
            "Only the owner may read a document.",
            "Archived documents cannot be read.",
        ]
        requirements = [
            dict(
                id=f"r{i + 1}",
                quote=s,
                start=self.policy.index(s),
                end=self.policy.index(s) + len(s),
                statement=s,
                categories=["permission"] if i == 0 else ["lifecycle"],
                implementation="datalog",
                relation="equivalent",
                assumptions=[],
                predicates=["Owner"] if i == 0 else ["Archived"],
            )
            for i, s in enumerate(statements)
        ]
        rules = [
            dict(id=f"rule{i + 1}", datalog=s)
            for i, s in enumerate(self.source.splitlines())
        ]
        content = dict(
            version=2,
            origin="reference",
            source=dict(
                name="example-policy.txt",
                text=self.policy,
                hash=fingerprint(self.policy),
                offsetUnit="unicode-code-point",
            ),
            contractHash=fingerprint(self.binding),
            requirements=requirements,
            rules=rules,
            coverage=[
                dict(id=f"r{i + 1}", ruleIds=[r["id"]]) for i, r in enumerate(rules)
            ],
            behaviors=[
                dict(
                    id="owner",
                    requirementIds=["r1"],
                    ruleIds=["rule1"],
                    kind="rule",
                    summary="A reader can open their own document, provided no refusal applies.",
                    conditions=[
                        "The selected document belongs to the authenticated reader."
                    ],
                ),
                dict(
                    id="archived",
                    requirementIds=["r2"],
                    ruleIds=["rule2"],
                    kind="rule",
                    summary="An archived document cannot be opened, even by its owner.",
                    conditions=[
                        "The current application record marks the selected document archived."
                    ],
                ),
            ],
            omittedRequirementIds=[],
            attempts=[],
            validation="static-only",
            runtimeInstalled=False,
        )
        return dict(content, id=fingerprint(content))

    def validate_setup(self, setup):
        if (
            not isinstance(setup, dict)
            or set(setup) != {f["name"] for f in self.setup_fields}
            or any(setup[f["name"]] not in f["options"] for f in self.setup_fields)
        ):
            raise ValueError("Choose a known reader, document and state.")

    def run(self, scenario, mode, seed, emit):
        self.validate_setup(scenario["setup"])
        if mode not in ("baseline", "protected"):
            raise ValueError("Unknown experiment mode.")
        setup = scenario["setup"]
        # New store for EACH run. Both modes call the same business function.
        store = {
            "doc-a": dict(owner="alice", content="Synthetic document A"),
            "doc-b": dict(owner="bob", content="Synthetic document B"),
        }
        row = store[setup["document"]]
        inputs = [fact("Owner", d, v["owner"]) for d, v in store.items()]
        if setup["state"] == "archived":
            inputs.append(fact("Archived", setup["document"]))
        executions = []

        def business(context):
            value = store[context["request"]["parameters"]["document"]]["content"]
            executions.append(value)
            return Applied(value)

        intent = dict(
            actor=setup["actor"],
            action="read",
            parameters={"document": setup["document"]},
        )
        if self._bundle is None:
            self._bundle = compile_policy(self.binding, self.source)
        started = perf_counter_ns()
        if mode == "protected":
            with PolicyRuntime(
                binding=self.binding,
                bundle=self._bundle,
                observations=[
                    ObservationSource(
                        "store",
                        ("Owner", "Archived"),
                        lambda _: Snapshot(
                            version="1", complete=True, facts=deepcopy(inputs)
                        ),
                    )
                ],
                operations=[Operation(action="read", execute=business)],
            ) as runtime:
                result = runtime.execute(intent)
                decision = result["decision"]
        else:
            business({"request": intent})
            decision = None
        elapsed = perf_counter_ns() - started
        # Independent fixture oracle uses business records, never the translated Datalog decision.
        should_allow = row["owner"] == setup["actor"] and setup["state"] == "active"
        snapshot = dict(
            binding=deepcopy(self.binding),
            source=self.source,
            inputs=inputs,
            versions={"store": "1"},
        )
        emit(
            dict(
                action="read",
                request=intent,
                outcome="executed" if executions else "blocked",
                value=executions[0] if executions else None,
                decision=decision,
                snapshot=snapshot,
                operationPathNs=elapsed,
                fixtureOracle=dict(
                    shouldAllow=should_allow,
                    actualViolation=bool(executions) and not should_allow,
                ),
                description=f"{setup['actor']} requested {setup['document']} ({setup['state']}).",
            )
        )
        return dict(
            completed=bool(executions),
            runner="scripted-example",
            seed=seed,
            modelUsed=False,
            initialStateHash=fingerprint(dict(store=store, inputs=inputs)),
            configurationHash=fingerprint(dict(runner="scripted-example", model=None)),
        )

    def inspect(self, snapshot, question):
        session = QuerySession(**snapshot)
        if question != "owners":
            raise ValueError("Unknown example question.")
        return session.query("?- Owner(Document, Actor).")
