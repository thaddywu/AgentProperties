"""Adaptation code: serve original payment tools with host-bound policy and paths."""

import argparse
import importlib.util
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from adapter import adapt
from money import minor_units

REVISION = '2fe55f85a51b65819222816cb5b5b71f7d594355'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--bank',type=Path,required=True,help='Original mock bank JSON, matching the reviewed initial facts')
    args = parser.parse_args()
    actual = subprocess.check_output(['git', '-C', str(args.upstream), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != REVISION: raise ValueError('Use the pinned upstream revision.')
    subprocess.run(['git', '-C', str(args.upstream), 'diff', '--quiet', 'HEAD', '--', 'mcp_servers', 'tool_log.py'], check=True)
    with TemporaryDirectory(prefix='scam-adapted-') as temporary:
        checkout = Path(temporary)
        shutil.copytree(args.upstream / 'mcp_servers', checkout / 'mcp_servers')
        shutil.copy(args.upstream / 'tool_log.py', checkout / 'tool_log.py')
        subprocess.run(['git', 'apply', str(Path(__file__).with_name('upstream.patch').resolve())], cwd=checkout, check=True)
        spec = importlib.util.spec_from_file_location('adapted_payments', checkout / 'mcp_servers/payments_server.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        # Adaptation code: bind the guard on the original registered MCP handlers.
        policy = adapt()
        module.policy_port = policy
        module.BANK_PATH = args.bank.resolve()
        try:
            # One startup consistency check, not a per-call bank-to-EDB producer.
            bank = module.load_bank()
            rows = policy.runtime.snapshot()
            configured = lambda name: [row['args'] for row in rows if row['predicate'] == name]
            account = bank['account']
            actual_payees = sorted([p['id'], p['account_number']] for p in bank['registered_payees'])
            if (actual_payees != sorted(configured('Payee'))
                    or configured('Balance') != [[str(minor_units(account['balance']))]]
                    or configured('DailyBudget') != [[str(minor_units(account['daily_limit']) - minor_units(account['transferred_today'])), str(minor_units(account['daily_limit']))]]):
                raise ValueError('The initial mock bank must match the reviewed policy inputs.')
            module.server.run(transport='stdio')
        finally: policy.runtime.close()


if __name__ == '__main__': main()
