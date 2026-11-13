"""Materialize the pinned dependency with its complete public patch; never edit the checkout."""

from contextlib import contextmanager
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'c5ca03d0cc35651fa49c8d637074e8258a1a715e'


@contextmanager
def adapted_checkout(path):
    path = Path(path).resolve()
    actual = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != REVISION:
        raise ValueError('Use the pinned upstream revision.')
    folders = ('core', 'fixtures', 'agents', 'phase1')
    subprocess.run(['git', '-C', str(path), 'diff', '--quiet', 'HEAD', '--', *folders], check=True)
    with TemporaryDirectory(prefix='labcluster-adapted-') as temporary:
        checkout = Path(temporary)
        for name in folders:
            shutil.copytree(path / name, checkout / name, ignore=shutil.ignore_patterns('__pycache__'))
        subprocess.run(['git', 'apply', str(ROOT / 'upstream.patch')], cwd=checkout, check=True)
        yield checkout
