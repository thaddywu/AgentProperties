"""Original bank JSON handlers plus incremental policy EDB evidence."""
import argparse
import asyncio
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

APP=Path(__file__).resolve().parents[1];sys.path.insert(0,str(APP))
from adapter import adapt
from tool_adapter import invoke
from money import minor_units
from policyscope.enforcement import caller_context,current_caller

parser=argparse.ArgumentParser();parser.add_argument('--upstream',type=Path,required=True)
args,remaining=parser.parse_known_args();sys.argv[1:]=remaining
REVISION='2fe55f85a51b65819222816cb5b5b71f7d594355'

class PaymentFacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        revision=subprocess.check_output(['git','-C',str(args.upstream),'rev-parse','HEAD'],text=True).strip()
        if revision!=REVISION:raise ValueError('Use the pinned upstream revision.')
        dependency=TemporaryDirectory(prefix='scam-edb-');cls.addClassCleanup(dependency.cleanup)
        root=Path(dependency.name)
        shutil.copytree(args.upstream/'mcp_servers',root/'mcp_servers')
        shutil.copy(args.upstream/'tool_log.py',root/'tool_log.py')
        subprocess.run(['git','apply',str(APP/'upstream.patch')],cwd=root,check=True)
        spec=importlib.util.spec_from_file_location('adapted_payments',root/'mcp_servers/payments_server.py')
        cls.payments=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.payments)
        spec=importlib.util.spec_from_file_location('adapted_assistant',root/'mcp_servers/assistant_server.py')
        cls.assistant=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.assistant)
    def setUp(self):
        self.policy=adapt(now=lambda:1000);self.addCleanup(self.policy.runtime.close)
        scope=caller_context('payments');scope.__enter__();self.addCleanup(scope.__exit__,None,None,None)
        self.payments.policy_port=self.policy
        self.assistant.policy_port=self.policy
        temporary=TemporaryDirectory();self.addCleanup(temporary.cleanup)
        sys.modules['tool_log'].LOG_PATH=Path(temporary.name)/'trace.jsonl'
        self.payments.BANK_PATH=Path(temporary.name)/'bank.json'
        self.assistant.DATA_DIR=Path(temporary.name)
        self.payments.BANK_PATH.write_text(json.dumps({'account':{'balance':5000,'daily_limit':1000,'transferred_today':100},
            'registered_payees':[{'id':'payee-1','name':'Synthetic Payee','account_number':'FAKE-ACCOUNT-0001'}], 'transactions':[]}))
        self.intent()
    def intent(self,identity='intent-1',cents=30000,recipient='payee-1',origin='user',purpose='transfer'):
        data=self.policy.data.reference('payment-details',identity)
        def add(facts):
            facts.put('TransferIntent',identity,recipient,cents,data)
            facts.put('Purpose',identity,purpose)
            facts.put('Source',origin,data)
            facts.put('UserConfirmation',identity,recipient,cents)
        self.policy.update(add);return data
    def transfer(self,amount=300,recipient='payee-1',identity='intent-1'):
        return self.payments.execute_transfer(recipient,amount,identity)
    def rows(self,name):return [f['args'] for f in self.policy.runtime.snapshot() if f['predicate']==name]

    def test_exact_confirmation_no_replay_and_atomic_balance_budget_consumption(self):
        self.assertEqual(self.transfer(amount=301)['status'],'denied')
        self.assertEqual(self.transfer(identity='invented')['status'],'denied')
        self.assertEqual(self.policy.runtime.effect_calls,0)
        self.assertEqual(self.transfer()['status'],'completed')
        self.assertEqual(self.rows('Balance'),[['470000']])
        self.assertEqual(self.rows('DailyBudget'),[['60000','100000']])
        self.assertEqual(self.rows('Consumed'),[['intent-1']])
        self.assertEqual(self.transfer()['status'],'denied')
        self.assertEqual(len(self.rows('Transfer')),1)

    def test_missing_confirmation_and_over_remaining_limit_never_execute(self):
        self.policy.update(lambda f:f.delete('UserConfirmation','intent-1','payee-1','30000'))
        self.assertEqual(self.transfer()['status'],'denied')
        self.intent('large',95000)
        self.assertEqual(self.transfer(amount=950,identity='large')['status'],'denied')
        self.assertEqual(self.policy.runtime.effect_calls,0)

    def test_untrusted_rewrite_keeps_origin_and_requires_review_and_cooling(self):
        data=self.policy.data.reference('payment-details','intent-1')
        parent=self.policy.data.reference('message','sms-1')
        def origin(f):f.put('Source','external_message',parent);f.put('DependsOn',data,parent)
        self.policy.update(origin)
        self.assertEqual(self.transfer()['status'],'denied')
        def review(f):f.put('IdentityVerified','intent-1','payee-1',30000);f.put('CoolingUntil','intent-1',1001)
        self.policy.update(review);self.assertEqual(self.transfer()['status'],'denied')
        self.policy.update(lambda f:f.put('CoolingUntil','intent-1',999))
        self.assertEqual(self.transfer()['status'],'completed')
        self.assertEqual(self.rows('CoolingUntil'),[['intent-1','999']])

    def test_unknown_recipient_verification_scope_and_principal_are_checked_in_dl(self):
        self.intent('unknown',30000,'FAKE-UNKNOWN')
        self.assertEqual(self.transfer(recipient='FAKE-UNKNOWN',identity='unknown')['status'],'denied')
        self.intent('verify',purpose='verification')
        self.assertEqual(self.transfer(identity='verify')['status'],'denied')
        with caller_context('assistant'):
            self.assertEqual(invoke(self.policy,'execute_transfer',{'recipient':'payee-1','amount':300,'transfer_request_id':'intent-1'},lambda:self.fail('Denied callback ran'))['status'],'denied')
        self.assertEqual(self.policy.runtime.effect_calls,0)

    def test_actual_mcp_registration_and_read_checks_use_same_edb(self):
        async def check():
            tools=await self.payments.server.list_tools()
            self.assertIn('transfer_request_id',next(t for t in tools if t.name=='execute_transfer').inputSchema['properties'])
            await self.payments.server.call_tool('execute_transfer',{'recipient':'payee-1','amount':300,'transfer_request_id':'intent-1'})
        asyncio.run(check())
        self.assertEqual(self.rows('Balance'),[['470000']])
        self.assertFalse(self.payments.check_daily_limit(700)['allowed'])
        self.assertEqual(json.loads(self.payments.BANK_PATH.read_text())['account']['balance'],4700)
        with caller_context('assistant'):public=self.assistant.list_payees()
        self.assertEqual(public['payees'][0]['account_masked'],'****0001')
        self.assertNotIn('FAKE-ACCOUNT-0001',str(public))

    def test_mcp_protocol_reads_actual_request_caller_instead_of_server_agent(self):
        from mcp.shared.memory import create_connected_server_and_client_session
        async def check():
            async with create_connected_server_and_client_session(self.payments.server) as client:
                arguments={'recipient':'payee-1','amount':300,'transfer_request_id':'intent-1'}
                missing=await client.call_tool('execute_transfer',arguments)
                self.assertTrue(missing.isError)
                denied=await client.call_tool('execute_transfer',arguments,meta={'caller':'assistant'})
                self.assertFalse(denied.isError)
                self.assertEqual((denied.structuredContent or json.loads(denied.content[0].text))['status'],'denied')
                allowed=await client.call_tool('execute_transfer',arguments,meta={'caller':'payments'})
                self.assertFalse(allowed.isError)
                self.assertEqual((allowed.structuredContent or json.loads(allowed.content[0].text))['status'],'completed')
        asyncio.run(check())
        self.assertEqual([event['principal'] for event in self.policy.events],['assistant','payments'])
        self.assertEqual(len(json.loads(self.payments.BANK_PATH.read_text())['transactions']),1)
        self.assertEqual(current_caller(),'payments')

    def test_invalid_currency_and_failed_fact_batch_leave_edb_unchanged(self):
        for value in [0.001,float('nan'),float('inf'),True]:
            with self.assertRaises(ValueError):minor_units(value)
        before=self.policy.runtime.snapshot()
        def fail(f):f.put('Balance',1);raise RuntimeError('Synthetic failure')
        with self.assertRaises(RuntimeError):self.policy.update(fail)
        self.assertEqual(self.policy.runtime.snapshot(),before)

    def test_original_bank_callback_runs_once_and_reads_do_not_refresh_edb(self):
        import ast
        original=ast.parse((args.upstream/'mcp_servers/payments_server.py').read_text())
        adapted=ast.parse(Path(self.payments.__file__).read_text())
        for name in ('load_bank','save_bank','lookup_recipient','check_daily_limit','execute_transfer'):
            body=lambda tree:ast.dump(ast.Module(body=next(n.body for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name),type_ignores=[]))
            self.assertEqual(body(original),body(adapted))
        self.assertEqual(self.policy.runtime._sources,[])
        self.assertEqual(self.transfer()['status'],'completed')
        bank=json.loads(self.payments.BANK_PATH.read_text())
        self.assertEqual(len(bank['transactions']),1)
        self.assertEqual(bank['account']['transferred_today'],400)
        self.assertEqual(self.transfer()['status'],'denied')
        self.assertEqual(json.loads(self.payments.BANK_PATH.read_text()),bank)

if __name__=='__main__':unittest.main()
