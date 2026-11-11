"""Adaptation code: wrap original MCP handlers and record confirmed result deltas."""
from functools import wraps
import inspect
from money import minor_units
from policy_runtime import caller_context, current_caller


def invoke(policy, name, arguments, function):
    """Bind actual arguments for policy evaluation, then run the original handler."""
    args = dict(arguments)
    if 'amount' in args:
        args['amount_minor'] = minor_units(args.pop('amount'))
    if 'transfer_request_id' in args:
        args['intent_id'] = args.pop('transfer_request_id')
    return policy.call(current_caller(), name, args, function)


def mcp_caller(server):
    """Read a supplied name from MCP _meta.caller, or from a direct-call scope."""
    try:
        context = server.get_context().request_context
    except ValueError:
        return current_caller()
    metadata = context.meta.model_dump() if context.meta is not None else {}
    name = metadata.get('caller')
    if not isinstance(name, str) or not name.strip():
        raise RuntimeError('MCP request must include a caller name in _meta.caller.')
    return name


def guarded(get_policy, server):
    """Decorate an existing tool without replacing its business implementation."""
    def decorate(function):
        name = function.__name__
        signature = inspect.signature(function)
        if name == 'execute_transfer':
            # Correlation metadata belongs to this wrapper, not the bank function.
            signature = signature.replace(parameters=[*signature.parameters.values(),
                inspect.Parameter('transfer_request_id', inspect.Parameter.POSITIONAL_OR_KEYWORD, default='', annotation=str)])
        @wraps(function)
        def call(*args, **kwargs):
            policy = get_policy()
            if policy is None:
                raise RuntimeError('The host must bind a policy before serving guarded tools.')
            captured = signature.bind(*args, **kwargs); captured.apply_defaults()
            actual = dict(captured.arguments)
            original = {key: value for key, value in actual.items() if key != 'transfer_request_id'}
            with caller_context(mcp_caller(server)):
                return invoke(policy, name, actual, lambda: function(**original))
        call.__signature__ = signature
        return call
    return decorate


def record_result(context, result):
    """Record only the confirmed transfer delta; never load or save the bank."""
    if context['request']['event'] != 'execute_transfer':
        return result
    facts = context['facts']
    parameters = context['request']['parameters']
    cents = int(parameters['amount_minor'])
    if minor_units(result['amount']) != cents or result['status'] != 'completed':
        raise ValueError('The transfer result differs from the authorized amount.')
    recipient = parameters['recipient']
    expected = next((account for identity, account in facts.rows('Payee') if recipient in (identity, account)), recipient)
    if result['to_account'] != expected:
        raise ValueError('The transfer result differs from the authorized recipient.')
    balance = int(facts.rows('Balance')[0][0])
    remaining, limit = facts.rows('DailyBudget')[0]
    facts.put('Balance', balance - cents)
    facts.put('DailyBudget', int(remaining) - cents, limit)
    facts.put('Consumed', parameters['intent_id'])
    facts.put('Transfer', result['transaction_id'], parameters['intent_id'], result['to_account'], cents, result['status'])
    return result
