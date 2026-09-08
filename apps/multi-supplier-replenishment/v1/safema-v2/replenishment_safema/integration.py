"""Install SafeMA v2 around one already-open frozen Base App instance."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from safema.runtime import SafeMARuntime, install
from safema.types import Effect

from replenishment.domain import OrderRejected

from .trusted_state import ReplenishmentTrustedStateResolver

INTEGRATION_ROOT = Path(__file__).resolve().parents[1]
MODELS = INTEGRATION_ROOT / "models"
POLICIES = INTEGRATION_ROOT / "policies"


def _denied(decision_id: int, reason: str, effect: Effect | None) -> OrderRejected:
    return OrderRejected(
        code="SAFEMA_POLICY_DENIED",
        message=f"decision {decision_id}: {reason}",
    )


def install_for_application(
    app: Any,
    *,
    owner_config_path: str | Path,
    metadata_db: str | Path,
    effect_models_path: str | Path = MODELS / "api-effects-v2.yaml",
    origin_models_path: str | Path = MODELS / "trusted-origins-v2.yaml",
    resolver_models_path: str | Path = MODELS / "trusted-state-resolvers-v2.yaml",
    policy_path: str | Path = POLICIES / "replenishment-purchase-v2.yaml",
) -> SafeMARuntime:
    resolver = ReplenishmentTrustedStateResolver(owner_config_path)
    runtime = install(
        effect_models_path=effect_models_path,
        origins_path=origin_models_path,
        resolver_models_path=resolver_models_path,
        policy_path=policy_path,
        metadata_db=metadata_db,
        trusted_resolvers={resolver.resolver_id: resolver.resolve},
        denial_handler=_denied,
    )
    actual_ids = set(app.services.suppliers)
    expected_ids = set(resolver.supplier_ids)
    if actual_ids != expected_ids:
        runtime.close()
        raise ValueError(
            f"application supplier instances do not match owner endpoints: "
            f"actual={sorted(actual_ids)} expected={sorted(expected_ids)}"
        )
    for supplier_id in sorted(expected_ids):
        runtime.bind_receiver(
            app.services.suppliers[supplier_id], {"supplier_id": supplier_id}
        )
    return runtime
