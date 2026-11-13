#!/usr/bin/env python3
"""Extract the pinned Linux x86_64 engine package after digest verification."""

import argparse
import hashlib
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from urllib.request import urlopen

URL = "https://github.com/souffle-lang/souffle/releases/download/2.5/x86_64-ubuntu-2204-souffle-2.5-Linux.deb"
SHA512 = "c21e2f8153c140499f5b2aa30a148dddec7be5663e36071466cdc225a6682f9fe699b939241c7c28258ee96d1e2c2fe5585e9e8e6b74fb20172f06d2b40774da"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    args = parser.parse_args()
    with TemporaryDirectory() as temporary:
        package = Path(temporary) / "souffle.deb"
        with urlopen(URL, timeout=60) as response:
            package.write_bytes(response.read())
        if hashlib.sha512(package.read_bytes()).hexdigest() != SHA512:
            raise ValueError("Native engine package digest mismatch.")
        args.directory.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["dpkg-deb", "-x", str(package), str(args.directory)], check=True
        )


if __name__ == "__main__":
    main()
