"""Trusted observations and additive wrappers. Authorization lives in frozen rules.dl.

Snapshots describe actual records; journal entries describe confirmed Store commits.
No agent-facing fact writer or alternative evaluator is provided.
"""
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps
import inspect
import sqlite3
import uuid
from contextlib import nullcontext

from policyweave.core.contracts import BridgeError
from policyweave.enforcement import caller_context
from policyweave.enforcement.caller import current_caller
from policyweave.enforcement.telemetry import current_trace
from policy_port.binding import make_policy, CONTRACT, CALLS

_INVOCATION = ContextVar('cluster_invocation', default=None)
_OBSERVATION = ContextVar('cluster_observation', default=None)
_MODEL = ContextVar('cluster_model', default=None)
_ACTIVE_KEYS = set()  # Only Settings explicitly constructed by this application.


def participant(actor):
    trace = current_trace()
    if trace:
        # Source responsibilities, including the explicit original environment actors.
        kinds = {'Professor':'agent', 'PhD':'agent', 'Master':'agent',
                 'Runner':'tool', 'LegacyCallback':'environment',
                 'ScenarioHarness':'environment', 'FaultInjector':'environment',
                 'OfflineAuditor':'observer', 'Evaluator':'observer',
                 'TracePersistence':'runtime', 'ProviderTransport':'tool',
                 'Unbound':'environment'}
        trace.participant(actor, kind=kinds.get(actor, 'environment'))
    return trace


def principal():
    try:
        return current_caller()
    except RuntimeError:
        return 'Unbound'


def completed(value):
    return not (isinstance(value, dict) and value.get('ok') is False)


def refusal(tool_name, feedback):
    """Keep native code only when its action/scope permits this disclosure."""
    from core.schemas import ApplicationError
    actor = principal()
    public_action = {'store_submit_effect':'submit_job', 'store_revise_effect':'revise_job',
                     'store_approve_effect':'approve_job', 'store_dispatch_effect':'dispatch_job',
                     'store_finish_effect':'finish_job'}.get(tool_name, tool_name)
    visible = set()
    if public_action in ('submit_job','revise_job'):
        visible |= {'QUOTA_EXCEEDED'}
    if public_action in ('revise_job',):
        visible |= {'NOT_QUEUED'}
    if public_action in ('approve_job','dispatch_job') and actor == 'Professor':
        visible |= {'NOT_QUEUED','STALE_TASK_VERSION','QUOTA_EXCEEDED',
                    'APPROVAL_REQUIRED_FOR_CURRENT_VERSION','PRIORITY_CONFLICT'}
    if public_action == 'finish_job':
        # These rules produce codes only for the owner or Professor.
        visible |= {'STALE_REPORT_IGNORED','NOT_RUNNING'}
    if tool_name in ('release_allocation','unsafe_release_by_node'):
        visible |= {'ALLOCATION_CHANGED'}
    codes = feedback['reasonCodes']
    safe = codes if codes and set(codes) <= visible else ['UNAVAILABLE']
    projected = {**feedback, 'reasonCodes':safe}
    if tool_name == 'read_job':
        # Exact original indistinguishable read protocol, no identifying metadata.
        return {'status':'UNAVAILABLE'}
    if tool_name in ('release_allocation','persist_trace_event','send_provider_request','export_evaluator_files'):
        if tool_name == 'send_provider_request':
            from agents.client import BackendError
            error = BackendError('Operation unavailable.')
        else:
            error = ApplicationError('Operation unavailable.')
        error.policy_feedback = projected
        raise error
    return {'ok':False, 'code':safe[0], 'policy':projected}


def field(rows, obj, key, value):
    definition = CONTRACT['fields'].get(key)
    if definition is None:
        return
    if definition['type'] == 'number':
        if type(value) is not int or not -(2**63) <= value < 2**63:
            return  # Invalid is missing, never rounded or treated as zero.
        encoded = str(value)
    else:
        from core.schemas import canonical
        encoded = value if isinstance(value, str) else canonical(value)
    rows.append({'predicate':'Field','args':[obj,key,encoded]})


class Session:
    def __init__(self):
        self.scope = uuid.uuid4().hex
        self.journal = []
        self.policies = {}

    def policy(self, layer):
        if layer not in self.policies:
            self.policies[layer] = make_policy(facts=self.facts, refusal=refusal,
                                                completed=completed, after=self.after, trace=True)
        return self.policies[layer]

    def facts(self, context, registry):
        from core.schemas import canonical
        observation = _OBSERVATION.get()
        if observation is None:
            raise RuntimeError('Missing actual boundary observation.')
        request = context['request']['id']
        rows = deepcopy(self.journal)
        state = observation.get('state')
        if state is not None:
            sid = self.scope + ':' + request
            field(rows, request, 'snapshot', sid)
            for collection in ('jobs','nodes','approvals','runs','receipts'):
                for index, record in enumerate(state[collection]):
                    oid = f'{sid}:{collection}:{index}'
                    field(rows, sid, collection, oid)
                    for key, value in record.items():
                        if key in CONTRACT['fields'] and key not in ('spec','outcome'):
                            field(rows, oid, key, value)
                    spec = record.get('spec', record.get('limits'))
                    if spec is not None:
                        field(rows, oid, 'spec', canonical(spec))
                        if collection == 'jobs':
                            for key, value in spec.items():
                                field(rows, oid, key, value)
        for key, value in observation.get('fields', {}).items():
            field(rows, request, key, value)
        observation['request_id'] = request
        return rows

    def after(self, context, result):
        # Only capture here. The surrounding SQLite commit has not happened yet.
        observation = _OBSERVATION.get()
        observation['request_id'] = context['request']['id']
        return result

    def committed(self, action, actor, observation, result):
        if not isinstance(result, dict) or result.get('ok') is not True:
            return
        record, kind, association = None, None, None
        if action == 'store_approve_effect' and 'approval' in result:
            record, kind, association = result['approval'], 'approve_job', 'approval_id'
        if action == 'store_runner_completion' and not result.get('duplicate'):
            record, kind, association = result.get('receipt'), 'record_completion', 'receipt_id'
        if record is not None:
            eid = observation['request_id']
            self.journal.append({'predicate':'Event','args':[eid,actor,kind]})
            field(self.journal, eid, 'outcome', 'applied')
            field(self.journal, eid, association, record['id'])


def session(store):
    if not hasattr(store, '_port_session'):
        store._port_session = Session()
    return store._port_session


def restore_callback_exception(error):
    """Keep actual original exceptions; never clear the runtime's uncertainty stop."""
    current = error
    while isinstance(current, BridgeError) and current.code == 'execution_uncertain':
        prior = current.__context__
        if prior is None:
            return
        current = prior
    if current is not error and not isinstance(current, BridgeError):
        raise current from None


def checked_call(owner, layer, action, args, body, values, observation, actor=None):
    participant(actor or principal())
    policy = owner.policy(layer)
    checked = policy(name=action, arguments=args)(body)
    token = _OBSERVATION.set(observation)
    try:
        with caller_context(actor or principal()):
            try:
                return checked(*values)
            except BridgeError as error:
                restore_callback_exception(error)
                raise
    finally:
        _OBSERVATION.reset(token)


def tool_dispatch(body):
    @wraps(body)
    def wrapped(self, name, args=None, parents=()):
        trace = participant(self.role)
        cm = trace.operation(self.role, name, args) if trace else nullcontext({})
        with cm as outcome, caller_context(self.role):
            result = body(self, name, args, parents)
            outcome['value'] = result[0]
            return result
    return wrapped


def tool_callback(store, actor, name, args, fn):
    """Retains the actual original fn(event_id), including inline fixture callbacks."""
    if name not in CALLS:
        return fn
    @wraps(fn)
    def wrapped(event_id):
        return checked_call(session(store), 'interface', name, args, fn, (event_id,),
                            {'state':store.snapshot()}, actor)
    return wrapped


def trace_tool(body):
    @wraps(body)
    def wrapped(self, actor, name, args, fn, parents=(), sources=(), visibility='PUBLIC', origin='application'):
        trace = participant(actor)
        # Tools.call already surrounds allowlist checks. Framework reuses matching operations.
        from policyweave.enforcement.telemetry import observe_operation
        with observe_operation(actor, name, args) as outcome, caller_context(actor):
            result = body(self, actor, name, args, fn, parents, sources, visibility, origin)
            if outcome is not None:
                outcome['value'] = result[0]
            return result
    return wrapped


_ACTIONS = {'submit':'store_submit_effect','revise':'store_revise_effect',
            'approve':'store_approve_effect','dispatch':'store_dispatch_effect',
            'record_completion':'store_runner_completion','finish':'store_finish_effect',
            'kill':'store_kill_cancel_effect','unsafe_release_by_node':'unsafe_release_by_node'}


def store_entry(body):
    signature = inspect.signature(body)
    @wraps(body)
    def wrapped(self, *args, **kwargs):
        bound = signature.bind(self, *args, **kwargs)
        bound.apply_defaults()
        values = dict(bound.arguments)
        values.pop('self')
        invocation = {'action':_ACTIONS[body.__name__], 'values':values,
                      'actor':principal(), 'observations':[]}
        token = _INVOCATION.set(invocation)
        trace = participant(invocation['actor'])
        try:
            result = body(self, *args, **kwargs)
            # body returns only after its original _mutate commits.
            for observation in invocation['observations']:
                session(self).committed(invocation['action'], invocation['actor'], observation, result)
            if trace:
                trace.event('state', invocation['actor'], data={
                    'operation':body.__name__, 'result':result, 'state':self.snapshot(),
                    'source':'original Store result after commit'})
            return result
        finally:
            _INVOCATION.reset(token)
    return wrapped


def mutation_callback(store, fn):
    invocation = _INVOCATION.get()
    if invocation is None:
        return fn  # Unregistered generic _mutate is a trusted-process bypass, reported.
    @wraps(fn)
    def wrapped(state):
        # Read the actual change(s) closure, including validate_spec's copied spec.
        values = {**invocation['values'], **{k:v for k,v in inspect.getclosurevars(fn).nonlocals.items()
                                            if k in invocation['values']}}
        invocation_fields = {'owner','job_id','run_id','node_id','receipt_id','reason'}
        fields = {k:v for k,v in values.items() if k in invocation_fields}
        if 'spec' in values:
            from core.schemas import canonical
            fields['spec'] = canonical(values['spec'])
            fields.update({k:v for k,v in values['spec'].items() if k in CONTRACT['fields']})
        observation = {'state':deepcopy(state), 'fields':fields}
        invocation['observations'].append(observation)
        action = invocation['action']
        arguments = ({k:values[k] for k in ('node_id','old_run_id')} if action == 'unsafe_release_by_node' else {})
        return checked_call(session(store), 'effect', action, arguments, fn, (state,), observation,
                            invocation['actor'])
    return wrapped


def release(body):
    @wraps(body)
    def wrapped(self, s, node, run, event_id, reason):
        observation = {'state':deepcopy(s), 'fields':{'node_id':node['id'], 'run_id':run['id']}}
        return checked_call(session(self), 'release', 'release_allocation', {}, body,
                            (self,s,node,run,event_id,reason), observation)
    return wrapped


def persist_event(body):
    signature = inspect.signature(body)
    @wraps(body)
    def wrapped(self, *args, **kwargs):
        bound = signature.bind(self, *args, **kwargs); bound.apply_defaults()
        payload = {k:v for k,v in bound.arguments.items() if k != 'self'}
        trace = participant(payload['actor'])
        # The backend already returned this visible decision. Observe it even if
        # the independent application-trace persistence gate refuses the payload.
        if trace and payload['kind'] == 'decision_summary':
            trace.model_output(payload['actor'], visible_observation(payload['outputs']['decision']),
                               stage=payload['inputs']['stage'])
        observation = {'fields':{'credential_occurrences':occurrences(payload)}}
        result = _bound_gate(session(self.store), 'persistence', 'persist_trace_event',
                             body, bound, observation, 'TracePersistence')
        if trace:
            if payload['kind'] not in ('decision_summary','message_sent','message_received','tool_call','tool_observation','decision_request'):
                trace.event('state',payload['actor'],data={'applicationEventId':result,
                            'kind':payload['kind'],'inputs':payload['inputs'],'outputs':payload['outputs']})
        return result
    return wrapped


def _bound_gate(owner, layer, action, body, bound, observation, actor):
    participant(actor)
    # Bind all arguments without changing the original body used by @policy coverage.
    checked = owner.policy(layer)(name=action, arguments={})(body)
    token = _OBSERVATION.set(observation)
    try:
        with caller_context(actor):
            try:
                return checked(*bound.args, **bound.kwargs)
            except BridgeError as error:
                restore_callback_exception(error)
                raise
    finally:
        _OBSERVATION.reset(token)


def occurrences(value):
    """Exact occurrences in actual serialized fields; no env/files/credential discovery."""
    def strings(item):
        if isinstance(item, str):
            yield item
        elif isinstance(item, dict):
            for name, child in item.items():
                yield from strings(name)
                yield from strings(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                yield from strings(child)
    return sum(text.count(key) for text in strings(value) for key in _ACTIVE_KEYS)


def visible_observation(value):
    """Exclude registered credential bytes from visible-output monitoring only.

    The original decision and the independent credential measurement stay intact.
    Unknown or transformed credentials remain a documented observation gap.
    """
    if isinstance(value, str):
        for key in sorted(_ACTIVE_KEYS, key=len, reverse=True):
            value = value.replace(key, '[redacted configured API key]')
        return value
    if isinstance(value, dict):
        return {visible_observation(k):visible_observation(v) for k,v in value.items()}
    if isinstance(value, list):
        return [visible_observation(v) for v in value]
    if isinstance(value, tuple):
        return tuple(visible_observation(v) for v in value)
    return value


def register_backend(body):
    @wraps(body)
    def wrapped(self, *args, **kwargs):
        result = body(self, *args, **kwargs)
        if self.settings.api_key:
            _ACTIVE_KEYS.add(self.settings.api_key)
        self._port_session = Session()
        return result
    return wrapped


def provider_request(body):
    signature = inspect.signature(body)
    @wraps(body)
    def wrapped(self, *args, **kwargs):
        bound = signature.bind(self,*args,**kwargs);bound.apply_defaults()
        observation = {'fields':{'credential_occurrences':occurrences(bound.arguments['body'])}}
        # Original 429 retry re-enters with a separate frozen policy instance.
        # Float timeout and retry budget never enter the parameter encoder.
        depth = getattr(self, '_port_request_depth', 0)
        self._port_request_depth = depth + 1
        try:
            result = _bound_gate(self._port_session, 'provider-'+str(depth), 'send_provider_request',
                                 body, bound, observation, 'ProviderTransport')
            return result
        finally:
            self._port_request_depth = depth
    return wrapped


def decide(body):
    @wraps(body)
    def wrapped(self, stage, extra=None, parents=()):
        participant(self.role)
        token = _MODEL.set((self.role,stage))
        try:
            return body(self,stage,extra,parents)
        finally:
            _MODEL.reset(token)
    return wrapped


def message(body):
    signature = inspect.signature(body)
    @wraps(body)
    def wrapped(self, *args, **kwargs):
        bound = signature.bind(self,*args,**kwargs);bound.apply_defaults()
        sender, recipient = bound.arguments['sender'], bound.arguments['recipient']
        before = len(self.trace.events)
        trace = current_trace()
        delivered = False
        try:
            result = body(*bound.args,**bound.kwargs)
            delivered = True
            return result
        finally:
            if trace:
                events = self.trace.events[before:]
                # Trace.add appends in memory before writing SQLite. Only a row
                # actually persisted by the original producer confirms a send.
                sent = None
                for event in events:
                    if event['kind'] != 'message_sent':
                        continue
                    try:
                        persisted = self.trace.store.db.execute(
                            'SELECT 1 FROM events WHERE seq=?', (event['seq'],)).fetchone()
                    except sqlite3.Error:
                        # Do not replace an original storage failure with an
                        # observer read failure or claim an unconfirmed send.
                        persisted = None
                    if persisted:
                        sent = event
                        break
                if sent:
                    participant(sender);participant(recipient)
                    trace.message(sender,[recipient],sent['inputs']['body'],phase='sent',message_id=sent['event_id'])
                    if delivered:
                        received = next(e for e in events if e['event_id']==result)
                        # Receipt is observed only after the original inbox append.
                        trace.message(sender,[recipient],received['inputs']['body'],phase='received',message_id=sent['event_id'])
    return wrapped


_EXPORT = None

def export_files(body):
    @wraps(body)
    def wrapped(data, out_dir):
        global _EXPORT
        from phase1.run import markdown
        if _EXPORT is None:
            _EXPORT = Session()
        observation = {'fields':{'credential_occurrences':occurrences([data,markdown(data)])}}
        return checked_call(_EXPORT,'export','export_evaluator_files',{},body,(data,out_dir),observation,'Evaluator')
    return wrapped


def observe_run(body):
    @wraps(body)
    def wrapped(*args, **kwargs):
        trace = participant('ScenarioHarness')
        if trace:
            trace.event('state','ScenarioHarness',data={'phase':'start','scenario':args[0] if args else kwargs.get('name')})
        result = body(*args,**kwargs)
        if trace:
            trace.event('state','ScenarioHarness',data={'phase':'final','state':result['final_state'],
                        'result':result['result'],'backend':result['backend'],
                        'fixtureNotice':'Offline backends are development fixtures, not live model execution.'})
        return result
    return wrapped
