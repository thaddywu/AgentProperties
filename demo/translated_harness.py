# Generated application-launch integration; original test helpers retained.
from pathlib import Path as _PolicyWeavePath
INPUT_DIRECTORY = _PolicyWeavePath(__file__).resolve().parent
ORIGINAL_APPLICATION = INPUT_DIRECTORY / "orig_app"
PORTED_APPLICATION = INPUT_DIRECTORY / "ported_app"

"""One LabCluster smoke scenario using its explicit offline backend."""
import importlib
import json
from pathlib import Path
import sys
CASES = [case["id"] for case in json.loads((INPUT_DIRECTORY / "test_cases.json").read_text())["cases"]]

def start_app():
    for name in list(sys.modules):
        if any((name == package or name.startswith(package + '.') for package in ('agents', 'core', 'phase1', 'policy_port'))):
            del sys.modules[name]
    sys.path.insert(0, str(APP_DIR.resolve()))
    importlib.invalidate_caches()
    from agents.deterministic import DeterministicBackend
    from phase1.run import run_scenario
    return (run_scenario, DeterministicBackend())

def check_result(result):
    jobs = result['final_state']['jobs']
    return result['result']['error'] is None and len(jobs) == 2 and ({job['owner'] for job in jobs} == {'Master', 'PhD'}) and all((job['state'] == 'COMPLETED' for job in jobs)) and all((node['run_id'] is None for node in result['final_state']['nodes']))

def _policyweave_execute(side, case, sample, output_dir):
    if case not in CASES:
        raise ValueError('Unknown scenario.')
    if type(sample) is not int or sample < 1:
        raise ValueError('--sample must be positive')
    artifacts = Path(output_dir) / 'artifacts'
    artifacts.mkdir(parents=True, exist_ok=True)
    previous_path = sys.path[:]
    try:
        run_scenario, backend = start_app()
        result = run_scenario(case, backend)
        complete = check_result(result)
        (artifacts / 'application.json').write_text(json.dumps(result, indent=2))
        return complete
    finally:
        sys.path[:] = previous_path

def _policyweave_dispatch(side, case, sample, output_dir):
    global APP_DIR
    APP_DIR = ORIGINAL_APPLICATION if side == 'original' else PORTED_APPLICATION
    return _policyweave_execute(side, case, sample, output_dir)


if __name__ == '__main__':
    from policyweave.workbench.runner import main as _policyweave_main
    raise SystemExit(_policyweave_main(_policyweave_dispatch, lambda result: result, cases=CASES))
