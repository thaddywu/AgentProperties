"""Adaptation code: guard structured completion reports before original delivery."""
from copy import deepcopy
from functools import wraps


def guard_completion_reports(error_type):
    """Keep the original Bus.send body and return value; gate only this protocol event."""
    def decorate(send):
        @wraps(send)
        def guarded(bus, sender, recipient, kind, body, parents=(), origin='application'):
            policy = getattr(bus.trace.store, 'policy', None)
            if policy is None or kind != 'COMPLETION_REPORT':
                return send(bus, sender, recipient, kind, body, parents, origin)
            # The trusted host supplies sender; body fields cannot replace its identity.
            payload = deepcopy(body)
            if not isinstance(payload, dict) or not isinstance(payload.get('job_id'), str):
                raise error_type('Completion report unavailable.')
            arguments = {'message_type': kind, 'recipient': recipient, 'job_id': payload['job_id']}

            def deliver():
                received = send(bus, sender, recipient, kind, payload, parents, origin)
                # Normalize only the private callback result for the existing tool adapter.
                return {'ok': True, 'message_event': received}

            result = policy.call(sender, 'send_message', arguments, deliver)
            if not result.get('ok'):
                raise error_type('Completion report unavailable.')
            return result['message_event']
        return guarded
    return decorate
