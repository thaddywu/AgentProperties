"""Role/group closure preserves authorization and responds to host updates."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from policyweave.enforcement import Policy
from policyweave.core.policy import compile_policy, policy_predicates


class MembershipTests(unittest.TestCase):
    def policy(self, source):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "rules.dl"
        path.write_text(source)
        return Policy(path, mechanisms=("capability",))

    def test_nested_roles_do_not_grant_permission_without_a_capability(self):
        policy = self.policy('''
PrincipalGroup("learner", "doctoral").
PrincipalGroup("doctoral", "students").
PrincipalGroup("students", "participants").
Allow(Q) :- Request(Q,P,"submit"), Can(P,"cluster","submit").
''')
        self.assertEqual(policy.runtime.query('?- InGroup("learner", G).')["rows"],
                         [["doctoral"], ["participants"], ["students"]])
        called = []
        policy.call("learner", "submit", {}, lambda: called.append("without_grant"))
        self.assertEqual(called, [])
        policy.put("Capability", "students", "cluster", "submit")
        policy.put("ResourceGroup", "cluster", "cpu-node")
        self.assertEqual(policy.runtime.query('?- Can("learner", "cpu-node", "submit").')["rows"], [[]])
        policy.call("learner", "submit", {}, lambda: called.append("submitted"))
        policy.call("outsider", "submit", {}, lambda: called.append("outsider"))
        self.assertEqual(called, ["submitted"])
        policy.delete("Capability", "students", "cluster", "submit")
        self.assertEqual(policy.runtime.query('?- Can("learner", "cpu-node", "submit").')["rows"], [])
        self.assertEqual(policy.runtime.query('?- InGroup("learner", "students").')["rows"], [[]])
        policy.call("learner", "submit", {}, lambda: called.append("after_revoke"))
        self.assertEqual(called, ["submitted"])

    def test_membership_removal_and_cycles_do_not_create_unrelated_members(self):
        policy = self.policy('''
Allow(Q) :- Request(Q,P,"read"), InGroup(P,"readers").
''')
        policy.put("PrincipalGroup", "reader", "team")
        policy.put("PrincipalGroup", "team", "readers")
        policy.put("PrincipalGroup", "readers", "team")
        self.assertEqual(policy.runtime.query('?- InGroup("outsider", "readers").')["rows"], [])
        policy.delete("PrincipalGroup", "reader", "team")
        self.assertEqual(policy.runtime.query('?- InGroup("reader", G).')["rows"], [])

    def test_rules_and_agent_facts_cannot_replace_membership_closure(self):
        source = 'InGroup(P,G) :- Request(Q,P,G).'
        binding = dict(version=1, id="membership", context="Synthetic membership authority test.",
            predicates=policy_predicates("", mechanisms=("capability",)), mechanisms=["capability"],
            decision=dict(request="Request", parameters="Parameter", allow="Allow", deny="Deny"), tests=[])
        with self.assertRaisesRegex(ValueError, "replace a foundation"):
            compile_policy(binding, source)
