"""Explicit configuration for the application (specification 8).

Configuration is a JSON or TOML file naming the database, the professor's
email address, the display time zone, and the concrete implementations of the
external interfaces.  Nothing experimental is hard-coded in the application:
swapping a real adapter for a local test double is a configuration change.

A component is named by a ``factory`` string of the form
``package.module:callable``.  The callable is invoked with the component's
``options`` as keyword arguments and must return an object satisfying the
matching protocol in :mod:`recsub.interfaces`.

Relative paths are resolved against the directory containing the
configuration file: this applies to ``database_path`` and to any option key
ending in ``_path``.
"""

from __future__ import annotations

import importlib
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .errors import ConfigError
from .interfaces import Clock, EmailGateway, PortalAgent, RequestSource
from .validation import _EMAIL

DEFAULT_CLOCK = "recsub.interfaces:system_clock"


@dataclass(frozen=True)
class ComponentSpec:
    """A configured implementation of one external interface."""

    factory: str
    options: Mapping[str, Any] = field(default_factory=dict)

    def build(self) -> Any:
        module_name, _, attribute = self.factory.partition(":")
        if not module_name or not attribute:
            raise ConfigError(
                f"factory {self.factory!r} must have the form 'package.module:callable'"
            )
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            raise ConfigError(f"cannot import module {module_name!r}: {exc}") from None
        try:
            factory = getattr(module, attribute)
        except AttributeError:
            raise ConfigError(
                f"module {module_name!r} has no attribute {attribute!r}"
            ) from None
        try:
            return factory(**dict(self.options))
        except ConfigError:
            raise
        except Exception as exc:
            raise ConfigError(f"factory {self.factory!r} failed: {exc}") from None


@dataclass(frozen=True)
class AppConfig:
    """Validated application configuration."""

    database_path: str
    professor_email: str
    display_time_zone: str
    request_sources: Sequence[ComponentSpec]
    email_gateway: ComponentSpec
    portal_agent: ComponentSpec
    clock: ComponentSpec
    source_path: Optional[str] = None

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.display_time_zone)


def load_config(path: str | Path) -> AppConfig:
    """Read and fully validate a configuration file."""
    config_path = Path(path).expanduser()
    if not config_path.is_file():
        raise ConfigError(f"configuration file not found: {config_path}")
    text = config_path.read_text(encoding="utf-8")
    suffix = config_path.suffix.lower()
    try:
        if suffix == ".toml":
            raw = tomllib.loads(text)
        elif suffix in (".json", ".jsonc", ""):
            raw = json.loads(text)
        else:
            raise ConfigError(
                f"unsupported configuration format {suffix!r}; use .json or .toml"
            )
    except (json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"{config_path} is not valid {suffix.lstrip('.') or 'json'}: {exc}") from None
    if not isinstance(raw, dict):
        raise ConfigError(f"{config_path} must contain a configuration table")
    return _build(raw, config_path.parent, str(config_path))


def _build(raw: Mapping[str, Any], base: Path, source: str) -> AppConfig:
    database_path = _require_str(raw, "database_path")
    professor_email = _require_str(raw, "professor_email")
    if not _EMAIL.match(professor_email):
        raise ConfigError(
            f"professor_email must be one email address, got {professor_email!r}"
        )
    time_zone = _require_str(raw, "display_time_zone")
    try:
        ZoneInfo(time_zone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ConfigError(f"display_time_zone {time_zone!r} is not a known time zone: {exc}") from None

    if "request_sources" not in raw:
        raise ConfigError("configuration is missing required key 'request_sources'")
    sources_raw = raw["request_sources"]
    if not isinstance(sources_raw, list):
        raise ConfigError("'request_sources' must be a list of component tables")
    sources = [
        _component(item, f"request_sources[{index}]", base)
        for index, item in enumerate(sources_raw)
    ]

    email_gateway = _component(_require_key(raw, "email_gateway"), "email_gateway", base)
    portal_agent = _component(_require_key(raw, "portal_agent"), "portal_agent", base)
    clock_raw = raw.get("clock", {"factory": DEFAULT_CLOCK})
    clock = _component(clock_raw, "clock", base)

    return AppConfig(
        database_path=str(_resolve(base, database_path)),
        professor_email=professor_email,
        display_time_zone=time_zone,
        request_sources=tuple(sources),
        email_gateway=email_gateway,
        portal_agent=portal_agent,
        clock=clock,
        source_path=source,
    )


def _require_key(raw: Mapping[str, Any], key: str) -> Any:
    if key not in raw:
        raise ConfigError(f"configuration is missing required key {key!r}")
    return raw[key]


def _require_str(raw: Mapping[str, Any], key: str) -> str:
    value = _require_key(raw, key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"configuration key {key!r} must be a non-empty string")
    return value.strip()


def _component(raw: Any, where: str, base: Path) -> ComponentSpec:
    if not isinstance(raw, Mapping):
        raise ConfigError(f"{where} must be a table with a 'factory' key")
    unknown = set(raw) - {"factory", "options"}
    if unknown:
        raise ConfigError(f"{where} has unknown key(s): {sorted(unknown)}")
    factory = raw.get("factory")
    if not isinstance(factory, str) or ":" not in factory:
        raise ConfigError(
            f"{where}.factory must be a string of the form 'package.module:callable'"
        )
    options = raw.get("options", {})
    if not isinstance(options, Mapping):
        raise ConfigError(f"{where}.options must be a table")
    resolved = {
        key: str(_resolve(base, value))
        if key.endswith("_path") and isinstance(value, str)
        else value
        for key, value in options.items()
    }
    return ComponentSpec(factory=factory, options=resolved)


def _resolve(base: Path, value: str) -> Path:
    candidate = Path(value).expanduser()
    return candidate if candidate.is_absolute() else (base / candidate).resolve()


# ---------------------------------------------------------------------------
# Component construction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Components:
    """The built external components required by the application."""

    request_sources: Sequence[RequestSource]
    email_gateway: EmailGateway
    portal_agent: PortalAgent
    clock: Clock


def build_components(config: AppConfig) -> Components:
    """Instantiate every configured external component, validating each one."""
    sources: list[RequestSource] = []
    seen_kinds: set[str] = set()
    for index, spec in enumerate(config.request_sources):
        source = spec.build()
        _check(source, RequestSource, f"request_sources[{index}]", spec)
        kind = getattr(source, "source_kind", None)
        if not isinstance(kind, str) or not kind.strip():
            raise ConfigError(
                f"request_sources[{index}] ({spec.factory}) must expose a non-empty "
                "'source_kind'"
            )
        if kind in seen_kinds:
            raise ConfigError(f"two request sources declare source_kind {kind!r}")
        seen_kinds.add(kind)
        sources.append(source)

    email_gateway = config.email_gateway.build()
    _check(email_gateway, EmailGateway, "email_gateway", config.email_gateway)
    portal_agent = config.portal_agent.build()
    _check(portal_agent, PortalAgent, "portal_agent", config.portal_agent)
    clock = config.clock.build()
    _check(clock, Clock, "clock", config.clock)

    return Components(
        request_sources=tuple(sources),
        email_gateway=email_gateway,
        portal_agent=portal_agent,
        clock=clock,
    )


def _check(component: object, protocol: type, where: str, spec: ComponentSpec) -> None:
    if not isinstance(component, protocol):
        raise ConfigError(
            f"{where} ({spec.factory}) does not implement the "
            f"{protocol.__name__} interface"
        )
