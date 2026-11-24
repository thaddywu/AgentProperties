"""Fixed-EDB contracts reject invented inputs, provenance and post-freeze edits."""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from policyweave.core.artifacts import files, save
from policyweave.core.policy import fingerprint, read_binding, validate_inputs, validate_state
from policyweave.policy_adder.binding import validate_inventory, validate_plan, validate_program
from policyweave.policy_adder.harness import _freeze, _json_stage, _rule_stage, assert_frozen, candidate_errors, check_recordings, planning_format


class BindingTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.original, self.framework = self.root / "original", self.root / "framework"
        self.original.mkdir()
        self.framework.mkdir()
        (self.root / "candidate").mkdir()
        self.tool = 'class Tools:\n    def call(self, name, args):\n        return self.backend(name, args["resource"])\n\ndef owner(record):\n    return record["owner"]\n'
        (self.original / "tool.py").write_text(self.tool)
        (self.original / "policy.md").write_text("P1. Only an owner may read.\nP2. Confirmation is required.\n")
        self.inventory = dict(boundaries=[dict(
            id="tools", kind="tool", file="tool.py", symbol="Tools.call", parameters=["name", "args"],
            identity="Host dispatch identity.", effect="Original backend callback.", outcome="Original returned value.",
            evidence=self.proof('return self.backend(name, args["resource"])'),
        )], gaps=["No human confirmation channel."])
        self.plan = dict(
            mechanisms=["observations"], configuration=[],
            calls=[dict(action="read", boundary="tools", parameters=[dict(
                name="resource", path=["resource"], type="symbol",
                evidence=self.proof('args["resource"]'),
            )], principal="Host dispatcher", before="Read actual owner", after="No state update",
                success="Actual read returned", failure="Preserve original failures")],
            observations=[dict(predicate="Field", name="owner", cardinality="one", type="symbol", unit=None, observed_at=None,
                meaning="Actual owner", scope="Object", missing="No grant", timing="before",
                producer="Stored record", evidence=self.proof('return record["owner"]'))],
            derived=[],
            invariants=[], agent_writes=[], requirements=[
                dict(id="p1", quote="P1. Only an owner may read.", disposition="supported", calls=["read"], reason="Actual owner join"),
                dict(id="p2", quote="P2. Confirmation is required.", disposition="unsupported", calls=[], reason="No confirmation producer"),
            ],
        )
        self.rules = 'Allow(Q) :- Request(Q,P,"read"), Parameter(Q,"resource",R), Field(R,"owner",P).\n'

    def proof(self, quote):
        return dict(origin="application", file="tool.py", quote=quote)

    def validate(self, raw=None):
        inventory = validate_inventory(self.inventory, self.original, self.framework, "policy.md")
        return validate_plan(raw or self.plan, inventory, self.original, self.framework, "policy.md")

    def test_source_backed_plan_compiles_only_stock_edb_and_planned_idb(self):
        plan = self.validate()
        self.assertEqual(plan["observationContract"], {"fields": {"owner": dict(cardinality="one", type="symbol", unit=None, observedAt=None)}})
        self.assertEqual(plan["callContract"], {"read": {"resource": "symbol"}})
        bundle = validate_program(self.rules, plan)
        self.assertEqual(set(bundle["binding"]["predicates"]), {"Request", "Parameter", "Allow", "Deny", "Field", "Event"})

    def test_call_roles_are_explicit_and_legacy_calls_still_require_gates(self):
        self.assertEqual(self.validate()["calls"][0].get("role", "gate"), "gate")
        raw = deepcopy(self.plan)
        raw["calls"][0]["role"] = "producer"
        self.assertEqual(self.validate(raw)["calls"][0]["role"], "producer")
        with self.assertRaisesRegex(ValueError,"producer-only"):
            validate_program(self.rules,self.validate(raw))
        raw["calls"][0]["role"] = "ignored"
        with self.assertRaisesRegex(ValueError, "role"):
            self.validate(raw)

    def test_producers_require_actual_execution_without_an_authorization_gate(self):
        self.inventory["boundaries"].append(dict(
            id="owner", kind="tool", file="tool.py", symbol="owner", parameters=["record"],
            identity="Host observation", effect="Read the original stored owner", outcome="Observed owner",
            evidence=self.proof('return record["owner"]'),
        ))
        raw = deepcopy(self.plan)
        raw["calls"].append(dict(action="observe_owner", boundary="owner", role="producer", parameters=[],
            principal="Host", before="Read record", after="Publish actual owner", success="Original returned owner", failure="Preserve errors"))
        raw["requirements"][0]["calls"].append("observe_owner")
        plan = self.validate(raw)
        for source in self.original.iterdir():
            (self.root/"candidate"/source.name).write_bytes(source.read_bytes())
        for name,value in [("source.json",{"files":files(self.original)}),
                           ("inventory.json",self.inventory),("binding-plan.json",plan)]:
            save(self.root/name,value)
        port = SimpleNamespace(output=self.root,runtime=self.framework)
        _freeze(port,plan)
        (self.root/"candidate/policy_port/rules.dl").write_text(self.rules)
        save(self.root/"workflow.json",dict(stages=dict(rules=dict(hash=fingerprint(self.rules)))))
        report = dict(policyTrajectories=[],trajectoryCoverage=dict(complete=True),
                      nativeBoundaryActions={"tools":{"read":1}},boundaryExecutions={"owner":1})
        errors = check_recordings(port,report)
        self.assertFalse(any("never exercised" in error or "producer" in error for error in errors),errors)
        report["boundaryExecutions"] = {}
        self.assertIn("Checks never executed the planned observation producer: owner",check_recordings(port,report))
        report["nativeBoundaryActions"] = {"tools":{"observe_owner":1}}  # a decision for another action
        errors = check_recordings(port,report)
        self.assertIn("Native gate checks never exercised the candidate boundary: tools",errors)
        self.assertTrue(any('by action: {"observe_owner": 1}' in e and "local variable" in e and "body" not in e for e in errors),errors)

    def test_native_initialization_failure_is_repaired_before_rules_freeze(self):
        plan = self.validate()
        for name,value in [("source.json",{"files":files(self.original)}),
                           ("inventory.json",self.inventory),("binding-plan.json",plan)]:
            save(self.root/name,value)
        port = SimpleNamespace(output=self.root,runtime=self.framework)
        _freeze(port,plan)
        calls = []
        save(self.root/"workflow.json",dict(stages={}))
        def session(workspace,prompt,name,*args,**kwargs):
            calls.append(prompt)
            self.assertFalse(json.loads((self.root/"workflow.json").read_text())["stages"].get("rules",{}).get("passed"))
            (self.root/"candidate/policy_port/rules.dl").write_text(self.rules)
            return 0
        port.session = session
        # Simulate an external native-process failure to verify stage recovery;
        # application conformance checks continue to require the real engine.
        with patch("policyweave.core.datalog.Souffle.evaluate",side_effect=[RuntimeError("native resource limit"),[]]):
            _rule_stage(port,1)
        self.assertEqual(len(calls),2)
        self.assertIn("native resource limit",calls[1])
        self.assertTrue(json.loads((self.root/"workflow.json").read_text())["stages"]["rules"]["passed"])

    def test_new_derived_schemas_are_rejected_even_with_a_justification(self):
        raw = deepcopy(self.plan)
        raw["derived"] = [dict(name="HasOwner", args=["Object"], types=["symbol"],
            meaning="Object has an owner", purpose="existence", justification="Absence check")]
        with self.assertRaises(ValueError):
            self.validate(raw)
        source = self.rules + '.decl HasOwner(Object:symbol)\nHasOwner(R) :- Field(R,"owner",P).\n'
        with self.assertRaises(ValueError):
            validate_program(source, self.validate())

    def test_role_configuration_is_explicit_source_backed_and_frozen(self):
        raw = deepcopy(self.plan)
        raw["mechanisms"].append("capability")
        raw["configuration"] = [dict(predicate="PrincipalGroup", args=["agent-a", "readers"],
            meaning="Configured reader membership", evidence=dict(origin="policy", file="policy.md", quote="P1. Only an owner may read."))]
        plan = self.validate(raw)
        source = 'PrincipalGroup("agent-a","readers").\n' + self.rules
        self.assertEqual(validate_program(source, plan)["binding"]["configuration"],
                         [{"predicate": "PrincipalGroup", "args": ["agent-a", "readers"]}])
        for changed in [self.rules, source.replace('"readers"', '"administrators"'),
                        source + 'Capability("agent-a","all","write").\n']:
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, "frozen role"):
                validate_program(changed, plan)
        raw["configuration"][0]["predicate"] = "Field"
        raw["configuration"][0]["args"] = ["job", "approved", "true"]
        with self.assertRaisesRegex(ValueError, "real producers"):
            self.validate(raw)

    def test_no_custom_schema_budget_or_invariant_registration(self):
        from policyweave.policy_adder.binding import MAX_DERIVED
        self.assertEqual(MAX_DERIVED, 0)
        raw = deepcopy(self.plan)
        raw["invariants"] = ["InventedViolation"]
        with self.assertRaises(ValueError):
            self.validate(raw)

    def test_discovery_checks_actual_signatures_symbols_and_unique_citations(self):
        for change in ("parameters", "symbol", "quote", "traversal"):
            raw = deepcopy(self.inventory)
            boundary = raw["boundaries"][0]
            if change == "parameters": boundary["parameters"] = ["invented"]
            elif change == "symbol": boundary["symbol"] = "Tools.missing"
            elif change == "quote": boundary["evidence"]["quote"] = "invented evidence"
            else: boundary["evidence"]["file"] = "../outside.py"
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_inventory(raw, self.original, self.framework, "policy.md")

    def test_every_original_policy_retains_a_disposition_including_unsupported(self):
        raw = deepcopy(self.plan)
        raw["requirements"].pop()
        with self.assertRaises(ValueError): self.validate(raw)

    def test_dispatcher_actions_cannot_be_hidden_behind_generic_call(self):
        source = self.tool.replace('        return self.backend', '        if name == "write":\n            return None\n        return self.backend')
        (self.original / "tool.py").write_text(source)
        with self.assertRaisesRegex(ValueError, "write"):
            self.validate()

    def test_source_prefix_is_normalized_without_weakening_exact_evidence(self):
        raw = deepcopy(self.plan)
        raw["observations"][0]["evidence"]["file"] = "original/tool.py"
        plan = self.validate(raw)
        self.assertEqual(plan["observations"][0]["evidence"]["file"], "tool.py")

    def test_internal_operation_mode_is_not_invented_as_an_extra_tool(self):
        source = 'def memory(action):\n    if action == "add":\n        return "saved"\n    return "contents"\n'
        (self.original / "memory.py").write_text(source)
        self.inventory["boundaries"] = [dict(
            id="memory", kind="tool", file="memory.py", symbol="memory", parameters=["action"],
            identity="Host identity", effect="Read or update existing memory", outcome="Actual return",
            evidence=dict(origin="application", file="memory.py", quote='if action == "add":'),
        )]
        raw = deepcopy(self.plan)
        raw["calls"][0].update(action="memory", boundary="memory", parameters=[dict(
            name="action", path=["action"], type="symbol",
            evidence=dict(origin="application", file="memory.py", quote="def memory(action):"),
        )])
        raw["requirements"][0]["calls"] = ["memory"]
        self.assertEqual([c["action"] for c in self.validate(raw)["calls"]], ["memory"])

    def test_data_only_repairs_preserve_unchanged_sections_and_revalidate_them(self):
        from policyweave.policy_adder.codex import CodexPort

        for name in ("core/foundations.json", "core/contracts.py", "enforcement/api.py",
                     "enforcement/fact_tools.py",
                     "runtime-guide.md", "porting-contract.md"):
            path = self.framework / name
            path.parent.mkdir(exist_ok=True)
            path.write_text("{}")
        save(self.root / "source.json", dict(policy="policy.md"))
        previous = deepcopy(self.inventory)
        previous["boundaries"][0]["parameters"] = ["invented"]
        previous["boundaries"] = [dict(deepcopy(previous["boundaries"][0]), id=f"boundary_{i}",
            identity="Synthetic caller. " * 60, effect="Synthetic effect. " * 60,
            outcome="Synthetic outcome. " * 60) for i in range(100)]
        save(self.root / "inventory-output-0.json", previous)
        self.assertGreater((self.root / "inventory-output-0.json").stat().st_size, 250_000)
        save(self.root / "inventory-validation-0.json", dict(error="Signature mismatch"))
        port = CodexPort.__new__(CodexPort)
        port.output, port.runtime, port.settings = self.root, self.framework, {}
        with patch("policyweave.adapters.compatible.Connection") as connection:
            connection.return_value.return_value = json.dumps(dict(boundaries=None, gaps=["Still missing confirmation"]))
            connection.return_value.usage = []
            result = port.plan("inventory", "repair", "inventory-attempt-1",
                               response_format=planning_format("inventory"))
            self.assertEqual(connection.call_args.args[0]["maxTokens"], 128_000)
            self.assertEqual(connection.call_args.args[0]["timeoutSeconds"], 600)
            self.assertEqual(result["boundaries"], previous["boundaries"])
            self.assertEqual(result["gaps"], ["Still missing confirmation"])
            self.assertIn("anyOf", connection.call_args.args[0]["responseFormat"]["json_schema"]["schema"]["properties"]["boundaries"])
            port.plan("inventory", "repair", "inventory-attempt-2",
                      response_format=planning_format("inventory"), repair_sections=["gaps"])
            properties = connection.call_args.args[0]["responseFormat"]["json_schema"]["schema"]["properties"]
            self.assertEqual(properties["boundaries"], {"type": "null"})
            self.assertEqual(properties["gaps"]["type"], "array")
            connection.return_value.return_value = json.dumps(self.inventory)
            with self.assertRaisesRegex(ValueError, "only the rejected sections"):
                port.plan("inventory", "repair", "inventory-attempt-3",
                          response_format=planning_format("inventory"), repair_sections=["gaps"])
        with self.assertRaisesRegex(ValueError, "signature"):
            validate_inventory(result, self.original, self.framework, "policy.md")

    def test_planning_keeps_explicit_large_budget_and_records_failed_call_diagnostics(self):
        from policyweave.policy_adder.codex import CodexPort

        for name in ("core/foundations.json", "core/contracts.py", "enforcement/api.py",
                     "enforcement/fact_tools.py", "runtime-guide.md", "porting-contract.md"):
            path = self.framework / name
            path.parent.mkdir(exist_ok=True)
            path.write_text("{}")
        save(self.root / "source.json", dict(policy="policy.md"))
        port = CodexPort.__new__(CodexPort)
        port.output, port.runtime = self.root, self.framework
        port.settings = dict(baseUrl="https://model.invalid/v1", modelId="fixture", maxTokens=64000)
        reply = dict(choices=[dict(finish_reason="length", message=dict(content="synthetic private partial"))],
                     usage=dict(completion_tokens=64000))
        with patch("policyweave.adapters.compatible.build_opener") as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = json.dumps(reply).encode()
            with self.assertRaisesRegex(RuntimeError, r"maxTokens \(64000\)"):
                port.plan("binding-plan", "plan", "binding-plan-attempt-0")
            payload = json.loads(opener.return_value.open.call_args.args[0].data)
            self.assertEqual(payload["max_completion_tokens"], 64000)
        diagnostic = json.loads((self.root / "binding-plan-attempt-0-error.json").read_text())
        self.assertEqual(diagnostic["kind"], "output_limit")
        self.assertEqual(diagnostic["completion_tokens"], 64000)
        self.assertEqual(json.loads((self.root / "binding-plan-attempt-0-usage.json").read_text()), [])
        self.assertFalse((self.root / "binding-plan-attempt-0-response.json").exists())
        self.assertNotIn("synthetic private partial", json.dumps(diagnostic))

    def test_large_source_backed_inventory_is_accepted_and_can_resume(self):
        raw = deepcopy(self.inventory)
        raw["boundaries"] = [dict(deepcopy(raw["boundaries"][0]), id=f"boundary_{i}",
            identity="Synthetic caller. " * 60, effect="Synthetic effect. " * 60,
            outcome="Synthetic outcome. " * 60) for i in range(100)]
        for source in self.original.iterdir():
            (self.root / "candidate" / source.name).write_bytes(source.read_bytes())
        save(self.root / "source.json", dict(files=files(self.original)))
        port = SimpleNamespace(output=self.root, plan=lambda *args, **kwargs: deepcopy(raw))
        validator = lambda value: validate_inventory(value, self.original, self.framework, "policy.md")
        inventory = _json_stage(port, "inventory", "discover", {}, validator, 0)
        self.assertEqual(len(inventory["boundaries"]), 100)
        self.assertGreater((self.root / "inventory-output-0.json").stat().st_size, 250_000)
        self.assertEqual(_json_stage(port, "inventory", "discover", {}, validator, 0), inventory)

    def test_extra_edb_input_redeclaration_and_observed_seeds_are_rejected(self):
        plan = self.validate()
        for source in [
            self.rules + '.decl Safe(Op:symbol)\n.input Safe\n',
            self.rules + '.decl Visible(P:symbol,R:symbol)\n.input Visible\n',
            self.rules + 'Field("document", "owner", "invented").\n',
            self.rules.replace('"owner"', '"unplanned_field"'),
        ]:
            with self.subTest(source=source), self.assertRaises(ValueError):
                validate_program(source, plan)

    def test_agent_cannot_plan_host_observation_writes(self):
        raw = deepcopy(self.plan)
        raw["agent_writes"] = [dict(principal="agent-a", kind="Field", subject="document", authority="self", evidence=self.proof('return record["owner"]'))]
        with self.assertRaises(ValueError): self.validate(raw)
        raw = deepcopy(self.plan)
        raw["observations"][0]["predicate"] = "Eligible"
        with self.assertRaises(ValueError): self.validate(raw)

    def test_removed_statement_mechanism_cannot_be_planned(self):
        raw = deepcopy(self.plan)
        raw["agent_writes"] = [dict(principal="agent-a", kind="statement", subject="document",
            authority="Own claim", evidence=dict(origin="policy", file="policy.md", quote="P1. Only an owner may read."))]
        with self.assertRaises(ValueError):self.validate(raw)
        raw = deepcopy(self.plan);raw["mechanisms"].append("statements")
        with self.assertRaises(ValueError):self.validate(raw)

    def test_numeric_field_units_and_time_survive_the_frozen_plan(self):
        (self.original / "tool.py").write_text(self.tool + '\ndef memory(record):\n    return record["memory_mb"], record["observed_at"]\n')
        raw = deepcopy(self.plan)
        for name, unit, clock in [("memory_mb", "MB", "observed_at"), ("observed_at", "unix_ms", None)]:
            raw["observations"].append(dict(
                predicate="Field", name=name, cardinality="one", type="number",
                unit=unit, observed_at=clock, meaning="Actual stored observation",
                scope="Object", missing="No grant", timing="before", producer="Stored record",
                evidence=self.proof(f'record["{name}"]'),
            ))
        plan = self.validate(raw)
        binding = validate_program(self.rules, plan)["binding"]
        definition = binding["observationContract"]["fields"]["memory_mb"]
        self.assertEqual(definition, dict(cardinality="one", type="number", unit="MB", observedAt="observed_at"))
        value = {"predicate": "Field", "args": ["document", "memory_mb", "8"]}
        with self.assertRaises(ValueError):
            validate_state(binding, [value])
        validate_state(binding, [value, {"predicate": "Field", "args": ["document", "observed_at", "1000"]}])
        value["args"][2] = "oops"
        with self.assertRaises(ValueError):
            validate_inputs(binding, [value])

    def test_runtime_contract_rejects_unknown_keys_units_and_contradictory_fields(self):
        bundle = validate_program(self.rules, self.validate())
        binding = bundle["binding"]
        for row in [
            {"predicate": "Field", "args": ["document", "not_frozen", "value"]},
            {"predicate": "Field", "args": ["document", "invented_metric", "1"]},
        ]:
            with self.assertRaises(ValueError): validate_inputs(binding, [row])
        with self.assertRaises(ValueError):
            validate_state(binding, [
                {"predicate": "Field", "args": ["document", "owner", "a"]},
                {"predicate": "Field", "args": ["document", "owner", "b"]},
            ])
        bad = deepcopy(binding)
        bad["callContract"]["read"]["resource"] = "invented_type"
        with self.assertRaises(ValueError): read_binding(bad)

    def test_frozen_source_plan_and_factory_changes_invalidate_the_port(self):
        plan = self.validate()
        for name, value in [("source.json", {"files": files(self.original)}), ("inventory.json", self.inventory), ("binding-plan.json", plan)]:
            save(self.root / name, value)
        port = SimpleNamespace(output=self.root, runtime=self.framework)
        _freeze(port, plan)
        self.assertEqual(assert_frozen(port)["callContract"], plan["callContract"])
        for path in [self.root / "binding-plan.json", self.root / "candidate/policy_port/binding.py", self.original / "tool.py"]:
            original = path.read_text()
            path.write_text(original + "\n")
            with self.subTest(path=path.name), self.assertRaises(ValueError): assert_frozen(port)
            path.write_text(original)

    def test_generated_helpers_without_original_boundary_instrumentation_are_rejected(self):
        plan = self.validate()
        for source in self.original.iterdir():
            (self.root / "candidate" / source.name).write_text(source.read_text())
        for name, value in [("source.json", {"files": files(self.original)}),
                            ("inventory.json", self.inventory), ("binding-plan.json", plan)]:
            save(self.root / name, value)
        port = SimpleNamespace(output=self.root, runtime=self.framework)
        _freeze(port, plan)
        (self.root / "candidate/policy_port/rules.dl").write_text(self.rules)
        save(self.root / "workflow.json", dict(stages=dict(rules=dict(hash=fingerprint(self.rules)))))
        self.assertIn("Planned boundary is not instrumented in the candidate: tools", candidate_errors(port))

    def test_partial_scope_requires_native_gates_without_forcing_unsupported_boundaries(self):
        source = self.tool + '\nasync def confirm(resource):\n    return resource\n'
        (self.original / "tool.py").write_text(source)
        self.inventory["boundaries"].append(dict(
            id="confirmation", kind="tool", file="tool.py", symbol="confirm", parameters=["resource"],
            identity="Reported caller", effect="Unsupported async effect", outcome="Original result",
            evidence=self.proof("async def confirm(resource):"),
        ))
        raw = deepcopy(self.plan)
        unsupported = deepcopy(raw["calls"][0])
        unsupported.update(action="confirm", boundary="confirmation")
        raw["calls"].append(unsupported)
        raw["requirements"][0].update(disposition="partial", reason="Owner check implemented; other paths remain gaps")
        raw["requirements"][1]["calls"] = ["confirm"]
        plan = self.validate(raw)
        for path in self.original.iterdir():
            (self.root / "candidate" / path.name).write_text(path.read_text())
        for name, value in [("source.json", {"files": files(self.original)}),
                            ("inventory.json", self.inventory), ("binding-plan.json", plan)]:
            save(self.root / name, value)
        port = SimpleNamespace(output=self.root, runtime=self.framework)
        _freeze(port, plan)
        (self.root / "candidate/policy_port/rules.dl").write_text(self.rules)
        save(self.root / "workflow.json", dict(stages=dict(rules=dict(hash=fingerprint(self.rules)))))
        self.assertEqual(candidate_errors(port), ["Planned boundary is not instrumented in the candidate: tools"])
        report = dict(policyTrajectories=[], trajectoryCoverage=dict(complete=True), nativeBoundaryActions={"tools": {"read": 2}})
        errors = check_recordings(port, report)
        self.assertFalse(any("never exercised" in e for e in errors), errors)
        self.assertTrue(any("complete actual policy gate evidence" in e for e in errors), errors)
        report["nativeBoundaryActions"] = {}
        errors = check_recordings(port, report)
        self.assertIn("Native gate checks never exercised the candidate boundary: tools", errors)
        self.assertNotIn("Native gate checks never exercised the candidate boundary: confirmation", errors)

    def test_planning_cannot_mutate_candidate_or_accept_changed_prior_plan(self):
        (self.root / "candidate/tool.py").write_text(self.tool)
        (self.root / "candidate/policy.md").write_text((self.original / "policy.md").read_text())
        save(self.root / "source.json", {"files": files(self.original)})
        def session(workspace, prompt, name, readonly):
            self.assertIn("candidate", readonly)
            (workspace / "candidate/tool.py").write_text("changed")
            save(workspace / "inventory-output-0.json", self.inventory)
            return 0
        port = SimpleNamespace(output=self.root, runtime=self.framework, session=session)
        with self.assertRaises(ValueError):
            _json_stage(port, "inventory", "discover", {}, lambda v: v, 0)
        self.assertFalse((self.root / "inventory.json").exists())
        save(self.root / "inventory.json", self.inventory)
        save(self.root / "workflow.json", {"stages": {"inventory": {"passed": True, "hash": "wrong"}}})
        with self.assertRaises(ValueError):
            _json_stage(port, "inventory", "discover", {}, lambda v: v, 0)
