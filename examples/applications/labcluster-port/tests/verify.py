"""Focused checks of original Store tools plus incremental policy EDB evidence."""
import argparse
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from policyscope.enforcement import BridgeError
from upstream import load_upstream

parser=argparse.ArgumentParser();parser.add_argument('--upstream',type=Path,required=True)
args,remaining=parser.parse_known_args();sys.argv[1:]=remaining

def spec(kind='CPU',cores=2):
    return {'title':'Synthetic task','node_type':kind,'cpu_cores':cores,'memory_gb':4,'runtime_minutes':10}

class LabFacts(unittest.TestCase):
    def setUp(self):
        self.app=load_upstream(args.upstream);self.addCleanup(self.app.close)
        self.master,self.phd,self.prof,self.runner=[self.app.tools(p) for p in ('Master','PhD','Professor','Runner')]
    def call(self,tool,name,arguments=None):return tool.call(name,arguments)[0]
    def submit(self,owner='Master',approve=True,request=None):
        job=self.call(self.master if owner=='Master' else self.phd,'submit_job',{'spec':request or spec()})['job']
        if approve:self.assertTrue(self.call(self.prof,'approve_job',{'job_id':job['id'],'expected_version':job['version'],'approve':True})['ok'])
        return job
    def dispatch(self,job):return self.call(self.prof,'dispatch_job',{'job_id':job['id']})['run']
    def complete(self,run):
        receipt=self.call(self.runner,'record_completion',{'run_id':run['id']})['receipt']
        result=self.call(self.master if run['owner']=='Master' else self.phd,'finish_job',{'job_id':run['job_id'],'receipt_id':receipt['id']})
        self.assertTrue(result['ok']);return receipt
    def state(self,job):return self.app.runtime.query(f'?- ResourceState("{job}", S).')['rows']

    def test_static_membership_and_quota_are_in_dl_and_denial_never_executes(self):
        self.assertTrue(hasattr(self.app,'store'))
        self.assertFalse((Path(__file__).resolve().parents[1]/'facts.py').exists())
        before=self.app.runtime.snapshot()
        self.assertFalse(self.call(self.master,'submit_job',{'spec':spec('GPU')})['ok'])
        self.assertFalse(self.call(self.master,'submit_job',{'spec':spec(cores=5)})['ok'])
        self.assertEqual(self.app.effect_calls,0);self.assertEqual(self.app.runtime.snapshot(),before)
        registry={r['predicate']:r for r in self.app.runtime.describe_predicates()}
        self.assertEqual(registry['PrincipalGroup']['registration'],'configuration')
        self.assertEqual(registry['Job']['registration'],'tool-input')

    def test_current_state_is_replaced_and_derived_answers_expire(self):
        job=self.submit();self.assertEqual(self.state(job['id']),[['QUEUED']])
        run=self.dispatch(job);self.assertEqual(self.state(job['id']),[['RUNNING']])
        self.assertEqual(self.app.runtime.query('?- Dispatchable(J).')['rows'],[])
        self.complete(run);self.assertEqual(self.state(job['id']),[['COMPLETED']])
        self.assertFalse(self.call(self.prof,'dispatch_job',{'job_id':job['id']})['ok'])
        self.assertEqual(self.app.runtime.query('?- AllocationViolation(R).')['rows'],[])

    def test_read_projection_and_revision_invalidate_old_approval(self):
        job=self.submit();calls=self.app.effect_calls
        self.assertEqual(self.call(self.phd,'read_job',{'job_id':job['id']}),self.call(self.phd,'read_job',{'job_id':'missing'}))
        self.assertEqual(self.app.effect_calls,calls)
        self.assertEqual(self.call(self.phd,'view')['jobs'],[])
        with self.assertRaises(self.app.schemas.ApplicationError):
            self.call(self.master,'approve_job',{'job_id':job['id'],'expected_version':1,'approve':True})
        changed=self.call(self.master,'revise_job',{'job_id':job['id'],'spec':spec(cores=3)})['job']
        self.assertEqual(changed['version'],2)
        self.assertFalse(self.call(self.prof,'dispatch_job',{'job_id':job['id']})['ok'])
        self.assertEqual(self.app.runtime.query('?- MatchingApproval(J).')['rows'],[])

    def test_priority_and_actual_skips_are_datalog_driven(self):
        master=self.submit()
        for _ in range(3):self.complete(self.dispatch(self.submit('PhD')))
        phd=self.submit('PhD')
        self.assertFalse(self.call(self.prof,'dispatch_job',{'job_id':phd['id']})['ok'])
        self.assertEqual(self.dispatch(master)['owner'],'Master')

    def test_provenance_and_old_notification_cannot_release_new_allocation(self):
        master=self.submit();old=self.dispatch(master)
        receipt=self.call(self.runner,'record_completion',{'run_id':old['id']})['receipt']
        self.assertTrue(self.call(self.prof,'kill_job',{'job_id':master['id'],'reason':'Synthetic stop'})['ok'])
        new=self.dispatch(self.submit('PhD'));before=self.app.runtime.snapshot()
        self.assertFalse(self.call(self.master,'finish_job',{'job_id':master['id'],'receipt_id':receipt['id']})['ok'])
        self.assertEqual(self.app.runtime.snapshot(),before)
        rows=self.app.runtime.query(f'?- RecordData("receipt", "{receipt["id"]}", D), Provenance(D, P).')['rows']
        self.assertEqual({r[1] for r in rows},{'Master'})
        self.assertEqual(self.state(new['job_id']),[['RUNNING']])

    def test_failed_stop_does_not_change_any_facts(self):
        job=self.submit();self.dispatch(job);before=self.app.runtime.snapshot()
        self.app.store.runner_stop_succeeds=False
        self.assertFalse(self.call(self.prof,'kill_job',{'job_id':job['id'],'reason':'Synthetic stop'})['ok'])
        self.assertEqual(self.app.runtime.snapshot(),before)

    def test_completion_report_owner_is_checked_before_trace_or_inbox_delivery(self):
        job=self.submit();run=self.dispatch(job)
        receipt=self.call(self.runner,'record_completion',{'run_id':run['id']})['receipt']
        body={'job_id':job['id'],'receipt_id':receipt['id'],'message':'Synthetic completion report'}
        before=self.app.runtime.snapshot()
        received=self.app.bus.send('Master','Professor','COMPLETION_REPORT',body)
        self.assertIsInstance(received,str)
        messages=self.app.bus.context('Professor')
        self.assertEqual(messages[-1]['received_event_id'],received)
        self.assertEqual(messages[-1]['message']['body'],body)
        self.assertEqual(self.app.runtime.snapshot(),before)
        events=list(self.app.trace.events);calls=self.app.effect_calls
        # A body-supplied sender cannot impersonate the host-bound caller.
        for invalid in [{**body,'sender':'Master'}, {**body,'job_id':'missing'}, {'message':'Missing job'}]:
            with self.assertRaises(self.app.schemas.ApplicationError):
                self.app.bus.send('PhD','Professor','COMPLETION_REPORT',invalid)
            self.assertEqual(self.app.bus.context('Professor'),messages)
            self.assertEqual(self.app.trace.events,events)
            self.assertEqual(self.app.effect_calls,calls)
        self.assertEqual(self.app.runtime.snapshot(),before)

    def test_completion_report_hook_preserves_original_message_body_and_other_protocols(self):
        import ast
        from inspect import getfile
        original=ast.parse((args.upstream/'core/messaging.py').read_text())
        adapted=ast.parse(Path(getfile(type(self.app.bus))).read_text())
        def send_body(tree):
            cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Bus')
            send=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='send')
            return ast.dump(ast.Module(body=send.body,type_ignores=[]))
        self.assertEqual(send_body(original),send_body(adapted))
        calls=len(self.app.policy.events)
        received=self.app.bus.send('PhD','Professor','SUBMISSION',{'message':'Synthetic submission'})
        self.assertEqual(self.app.bus.context('Professor')[-1]['received_event_id'],received)
        self.assertEqual(len(self.app.policy.events),calls)

    def test_postcondition_failure_stops_session_after_original_store_effect(self):
        original=self.app.policy.put;job=self.submit()
        def broken(name,*values):
            if name=='Node' and values[4]:
                values=(*values[:5],int(values[5])+1)
            return original(name,*values)
        before=self.app.runtime.snapshot()
        with patch.object(self.app.policy,'put',broken),self.assertRaises(BridgeError) as error:self.dispatch(job)
        self.assertEqual(error.exception.code,'execution_uncertain')
        self.assertEqual(self.app.runtime.snapshot(),before)
        self.assertEqual(self.app.store.snapshot()['jobs'][0]['state'],'RUNNING')
        with self.assertRaises(BridgeError) as stopped:self.dispatch(job)
        self.assertEqual(stopped.exception.code,'session_failed')

    def test_original_store_is_unchanged_and_no_snapshot_producer_is_registered(self):
        import inspect
        original=(args.upstream/'core/store.py').read_text()
        self.assertEqual(Path(inspect.getfile(type(self.app.store))).read_text(),original)
        self.assertEqual(self.app.runtime._sources,[])
        job=self.submit()
        stored=self.app.store.snapshot()['jobs'][0]
        self.assertEqual(stored['id'],job['id'])
        self.assertEqual(self.app.runtime.query('?- Job(J, O, V, H, R).')['rows'][0][:3],
                         [stored['id'],stored['owner'],str(stored['version'])])

if __name__=='__main__':unittest.main()
