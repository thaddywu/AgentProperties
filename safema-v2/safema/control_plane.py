"""Trusted administrative resource registration outside the Base App."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .registry import MetadataRegistry
from .types import Resource
from .values import resolve_identity


class TrustedControlPlane:
    """Explicit trusted boundary; callers are authenticated by deployment assumption."""

    def __init__(self, metadata_db: str | Path) -> None:
        self.registry = MetadataRegistry(metadata_db)

    def register_resource(
        self,
        value: Any,
        *,
        resource_class: str,
        attributes: dict[str, Any],
        identity_resolver: str = "file_sha256",
    ) -> int:
        identity = resolve_identity(value, identity_resolver)
        return self.registry.bind_resource(
            Resource(identity=identity, object_class=resource_class, attributes=attributes),
            origin_id="safema.trusted_control_plane",
        )

    def close(self) -> None:
        self.registry.close()

    def __enter__(self) -> "TrustedControlPlane":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-db", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--resource-class", required=True)
    parser.add_argument("--attributes-json", required=True)
    args = parser.parse_args(argv)
    attributes = json.loads(args.attributes_json)
    if not isinstance(attributes, dict):
        parser.error("--attributes-json must decode to an object")
    with TrustedControlPlane(args.metadata_db) as control_plane:
        binding_id = control_plane.register_resource(
            args.path,
            resource_class=args.resource_class,
            attributes=attributes,
        )
    print(json.dumps({"binding_id": binding_id}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
