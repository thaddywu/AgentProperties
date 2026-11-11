"""Offline conformance of the small policy surface and native execution boundary."""

from copy import deepcopy
from pathlib import Path
import os
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from policy_runtime import Applied, BridgeError, DataRegistry, NotApplied, ObservationSource, Operation, Policy, PolicyClient, PolicyRuntime, Snapshot, Unknown, compile_policy, mechanism_predicates, policy_predicates
from policy_runtime.datalog import Souffle, decode, encoded_fact, parse, stratify


def f(name, *args):
    return {"predicate": name, "args": list(args)}


POLICY = 'Allow(Q) :- Request(Q, P, "read"), Parameter(Q, "resource", R), Grant(P, R).\nSeen(R) :- Grant(P, R).'


def binding():
    return {"version": 1, "id": "native-test", "context": "Synthetic document service.",
            "predicates": {**policy_predicates(''),
                           "Grant": {"kind": "input", "args": ["Principal", "Resource"], "meaning": "Backend grant."},
                           "Seen": {"kind": "derived", "args": ["Resource"], "meaning": "Derived objects."}},
            "decision": {"request": "Request", "parameters": "Parameter", "allow": "Allow", "deny": "Deny"},
            "tests": [{"name": "grant", "inputs": [f("Grant", "reader", "item")], "request": {"actor": "reader", "action": "read", "resource": "item"}, "allowed": True},
                      {"name": "no-grant", "inputs": [], "request": {"actor": "reader", "action": "read", "resource": "item"}, "allowed": False}]}


class NativeTests(unittest.TestCase):
    def runtime(self, **kwargs):
        b = binding()
        kwargs.setdefault("inputs", [])
        return PolicyRuntime(binding=b, bundle=compile_policy(b, POLICY), operations=[Operation("read", lambda _: Applied("body"))], **kwargs)

    def test_safe_grammar_and_input_authority(self):
        for source in ['.include "private"', 'Grant("reader", "item").', '?- Grant(P, R).',
                       'Grant(P, R) :- Request(Q, P, E), Parameter(Q, "resource", R).',
                       'Allow(Q) :- not Grant(P, R).',
                       'Allow(Q) :- Request(Q, P, E), not Seen(P).\nSeen(P) :- Request(Q, P, E), not Allow(Q).']:
            with self.subTest(source=source), self.assertRaises(ValueError): compile_policy(binding(), source)
        for records in [[f("Request", "fake", "reader", "read")], [f("Allow", "fake")]]:
            with self.assertRaises(ValueError): self.runtime(inputs=records)

    def test_colocated_declarations_cannot_change_trusted_schema(self):
        source = '.decl Grant(Principal:symbol, Resource:symbol) // Backend grants.\n.input Grant\n'+POLICY
        self.assertEqual(compile_policy(binding(), source)["source"], source)
        for bad in [source.replace('.input Grant', ''), source.replace('Principal:symbol', 'Impostor:symbol'), '.input Missing', '.decl X(A:number)']:
            with self.subTest(source=bad), self.assertRaises(ValueError): compile_policy(binding(), bad)

    def test_symbols_and_native_integer_comparisons(self):
        values = ['UPPERCASE', 'c:prefix', 'quote"tab\tline\n', '中文😀', '\\", dangerous(). //', '', '10', '-1']
        rules, _ = parse('Seen(R) :- Grant(P, R).')
        stratify(rules)
        closure = Souffle().evaluate([encoded_fact(f("Grant", "reader", v)) for v in values], rules)
        self.assertEqual({decode(a["args"][0]) for a in closure if a["predicate"] == "Seen"}, set(values))
        rules, _ = parse('Seen(N) :- Grant(P, N), N >= 0, N <= 10.')
        stratify(rules)
        closure = Souffle().evaluate([encoded_fact(f("Grant", "reader", v)) for v in values], rules)
        self.assertEqual({decode(a["args"][0]) for a in closure if a["predicate"] == "Seen"}, {'10'})

    def test_simple_connection_updates_facts_and_recomputes_derived_rows(self):
        grants, calls = [f("Grant", "reader", "item")], []
        def read(context):
            calls.append(context["derived"]["Seen"])
            grants.clear()
            return Applied("body")
        b = binding()
        with PolicyRuntime(binding=b, bundle=compile_policy(b, POLICY), observations=[ObservationSource("backend", ("Grant",), lambda _: Snapshot("v1", True, grants))], operations=[Operation("read", read, reads=("Seen",))]) as runtime:
            result = runtime.bind("reader").execute("read", "item")
            self.assertEqual(set(result), {"allowed", "attemptId", "value"})
            self.assertEqual(calls, [(("item",),)])
            self.assertEqual(runtime.query('?- Seen(R).')["rows"], [])
            self.assertFalse(runtime.bind("reader").execute("read", "item")["allowed"])
            self.assertFalse(hasattr(runtime.bind("reader"), "query"))

    def test_no_reader_or_observer_is_required(self):
        with self.runtime(inputs=[f("Grant", "reader", "item")]) as runtime:
            self.assertTrue(runtime.bind("reader").execute("read", "item")["allowed"])
            before = runtime.snapshot()
            runtime.what_if({"actor": "reader", "action": "read", "resource": "item"}, [])
            self.assertEqual(runtime.snapshot(), before)

    def test_request_can_have_no_resource_and_identity_is_immutable(self):
        b = binding(); b['tests'] = []
        source = 'Allow(Q) :- Request(Q, P, "ping").'
        def ping(context):
            with self.assertRaises(TypeError): context['request']['actor'] = 'other'
            return Applied('pong')
        runtime = PolicyRuntime(binding=b, bundle=compile_policy(b, source), inputs=[], operations=[Operation("ping", ping)])
        self.assertTrue(runtime.bind('reader').execute('ping')['allowed'])

    def test_failed_or_forged_observation_never_calls_business_function(self):
        for records in [[f('Allow', 'fake')], None]:
            calls = []
            b = binding()
            runtime = PolicyRuntime(binding=b, bundle=compile_policy(b, POLICY), observations=[ObservationSource("backend", ("Grant",), lambda _: Snapshot("v1", True, records))], operations=[Operation("read", lambda _: calls.append(1))])
            with self.assertRaises(BridgeError): runtime.bind('reader').execute('read', 'item')
            self.assertEqual(calls, [])

    def test_uncertainty_stops_session_without_recovery_relations_or_replay(self):
        b = binding(); calls = []
        def effect(_): calls.append(1); return Unknown()
        runtime = PolicyRuntime(binding=b, bundle=compile_policy(b, POLICY), inputs=[f('Grant', 'reader', 'item')], operations=[Operation('read', effect)])
        with self.assertRaises(BridgeError) as failure: runtime.bind('reader').execute('read','item')
        self.assertEqual(failure.exception.code,'execution_uncertain')
        with self.assertRaises(BridgeError): runtime.bind('reader').execute('read','item')
        self.assertEqual(calls,[1])
        self.assertFalse(hasattr(runtime,'reconcile'))
        self.assertFalse(any(f['predicate']=='ResourceRecovery' for f in runtime.snapshot()))

    def test_pinned_analysis_has_no_effect_and_keeps_old_input_version(self):
        grants = [f('Grant','reader','item')]
        b = binding()
        runtime = PolicyRuntime(binding=b,bundle=compile_policy(b,POLICY), observations=[ObservationSource('backend', ('Grant',), lambda _: Snapshot('v1', True, grants))],operations=[Operation('read',lambda _:Applied('body'))])
        analysis = runtime.capture({'actor':'reader','action':'read','resource':'item'})
        grants.clear()
        self.assertEqual(analysis.query('?- Seen(R).')['rows'],[['item']])
        self.assertFalse(runtime.bind('reader').execute('read','item')['allowed'])
        self.assertFalse(hasattr(analysis,'execute'))

    def test_foundations_cannot_be_redefined(self):
        b = binding(); b['mechanisms']=['provenance'];b['predicates'].update(mechanism_predicates('provenance'))
        with self.assertRaises(ValueError): compile_policy(b,POLICY+'\nProvenance(D,P) :- Source(P,D).')

    def test_data_handles_distinguish_versions_and_are_reversible(self):
        data = DataRegistry()
        first=data.reference('pdf','report','v1');second=data.reference('pdf','report','v2')
        self.assertNotEqual(first,second)
        self.assertEqual(first,data.reference('pdf','report','v1'))
        self.assertEqual(data.describe(first),{'kind':'pdf','key':'report','version':'v1'})

    def test_numeric_input_types_reject_bad_values_before_any_effect(self):
        b = binding()
        b['tests'] = []
        b['predicates']['Grant']['types'] = ['symbol', 'number']
        for value in ['01', 'not-a-number', '9223372036854775808']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                PolicyRuntime(binding=b, bundle=compile_policy(b, POLICY), inputs=[f('Grant', 'reader', value)])

    def test_file_policy_owns_configuration_and_wraps_an_existing_tool(self):
        source='''\n.decl Grant(Principal:symbol, Resource:symbol)\n.input Grant\nGrant("reader", "item").\nAllow(Q) :- Request(Q, P, "read"), Parameter(Q,"document",D), Grant(P,D).'''
        with TemporaryDirectory() as directory:
            path=Path(directory)/'policy.dl';path.write_text(source)
            policy=Policy(path)
            calls=[]
            read=lambda _:calls.append('read') or {'body':'synthetic'}
            self.assertEqual(policy.wrap('reader','read',{'document':'item'},read)('upstream-1'),{'body':'synthetic'})
            self.assertEqual(policy.wrap('other','read',{'document':'item'},read)('upstream-2')['code'],'UNAVAILABLE')
            self.assertEqual(calls,['read'])
            self.assertNotEqual(policy.events[0]['id'],policy.events[1]['id'])

    def test_worker_preserves_the_same_native_contract(self):
        b = binding()
        with patch.dict(os.environ,{'PYTHONPATH':str(Path(__file__).resolve().parents[1])}), PolicyClient(binding=b,bundle=compile_policy(b,POLICY),
                observations=[ObservationSource('directory',('Grant',),lambda _:Snapshot('v1',True,[f('Grant','reader','item')]))],
                operations=[Operation('read',lambda _:Applied('body'))]) as client:
            self.assertTrue(client.bind('reader').execute('read','item')['allowed'])
            self.assertFalse(hasattr(client,'reconcile'))


if __name__=='__main__': unittest.main()
