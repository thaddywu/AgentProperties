"""Adaptation code: compose original offline agents and Store with a policy hook."""
import argparse
import json
import sys
from adapter import adapt
from tools.upstream_checkout import adapted_checkout


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream',required=True)
    parser.add_argument('--scenario',default='T1_priority_queue')
    args=parser.parse_args()
    with adapted_checkout(args.upstream) as checkout:
        sys.path.insert(0,str(checkout))
        from agents.deterministic import DeterministicBackend
        from core.store import Store
        from core.tracing import Trace
        from core.messaging import Bus
        from phase1.scenarios import Scenario
        store=Store();store.initialize()
        # Adaptation code: attach the policy without changing Store business methods.
        policy=adapt();store.policy=policy
        try:
            trace=Trace(store)
            Scenario(DeterministicBackend(),store,trace,Bus(trace)).execute(args.scenario)
            print(json.dumps({'scenario':args.scenario,'guardedCalls':len(policy.events),
                              'jobStates':{j['id']:j['state'] for j in store.snapshot()['jobs']}},indent=2))
        finally:
            policy.runtime.close();store.close()


if __name__=='__main__':main()
