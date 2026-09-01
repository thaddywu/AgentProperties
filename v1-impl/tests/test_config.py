"""Specification 8 — configuration validation and component construction."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from recsub.config import build_components, load_config
from recsub.errors import ConfigError

VALID = {
    "database_path": "recsub.sqlite3",
    "professor_email": "professor@example.edu",
    "display_time_zone": "America/New_York",
    "request_sources": [
        {
            "factory": "recsub.testing.doubles:json_file_request_source",
            "options": {"source_kind": "email_inbox", "events_path": "events.json"},
        }
    ],
    "email_gateway": {"factory": "recsub.testing.doubles:recording_email_gateway"},
    "portal_agent": {"factory": "recsub.testing.doubles:recording_portal_agent"},
    "clock": {
        "factory": "recsub.testing.doubles:fixed_clock",
        "options": {"instant": "2026-11-01T12:00:00Z"},
    },
}


def write_config(tmp_path: Path, **overrides) -> Path:
    data = json.loads(json.dumps(VALID))
    for key, value in overrides.items():
        if value is _MISSING:
            data.pop(key, None)
        else:
            data[key] = value
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class _Missing:
    pass


_MISSING = _Missing()


class TestLoading:
    def test_a_valid_configuration_loads(self, tmp_path: Path):
        config = load_config(write_config(tmp_path))

        assert config.professor_email == "professor@example.edu"
        assert config.display_time_zone == "America/New_York"
        assert len(config.request_sources) == 1

    def test_relative_paths_resolve_against_the_configuration_file(self, tmp_path: Path):
        config = load_config(write_config(tmp_path))

        assert config.database_path == str(tmp_path / "recsub.sqlite3")
        assert config.request_sources[0].options["events_path"] == str(
            tmp_path / "events.json"
        )

    def test_toml_is_supported(self, tmp_path: Path):
        path = tmp_path / "config.toml"
        path.write_text(
            """
database_path = "recsub.sqlite3"
professor_email = "professor@example.edu"
display_time_zone = "UTC"

[[request_sources]]
factory = "recsub.testing.doubles:json_file_request_source"
options = { source_kind = "email_inbox", events_path = "events.json" }

[email_gateway]
factory = "recsub.testing.doubles:recording_email_gateway"

[portal_agent]
factory = "recsub.testing.doubles:recording_portal_agent"
""",
            encoding="utf-8",
        )

        config = load_config(path)

        assert config.display_time_zone == "UTC"
        assert config.clock.factory == "recsub.interfaces:system_clock"  # the default

    def test_a_missing_file_is_reported(self, tmp_path: Path):
        with pytest.raises(ConfigError, match="not found"):
            load_config(tmp_path / "absent.json")

    @pytest.mark.parametrize(
        "key",
        [
            "database_path",
            "professor_email",
            "display_time_zone",
            "request_sources",
            "email_gateway",
            "portal_agent",
        ],
    )
    def test_every_required_key_is_checked(self, tmp_path: Path, key: str):
        with pytest.raises(ConfigError, match=key):
            load_config(write_config(tmp_path, **{key: _MISSING}))

    def test_an_invalid_professor_address_is_rejected(self, tmp_path: Path):
        with pytest.raises(ConfigError, match="professor_email"):
            load_config(write_config(tmp_path, professor_email="not-an-address"))

    def test_an_unknown_time_zone_is_rejected(self, tmp_path: Path):
        with pytest.raises(ConfigError, match="time zone"):
            load_config(write_config(tmp_path, display_time_zone="Mars/Olympus_Mons"))

    def test_a_malformed_component_is_rejected(self, tmp_path: Path):
        with pytest.raises(ConfigError, match="factory"):
            load_config(write_config(tmp_path, email_gateway={"factory": "nocolon"}))

    def test_invalid_json_is_reported(self, tmp_path: Path):
        path = tmp_path / "config.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config(path)


class TestComponentConstruction:
    def test_components_are_built_from_the_configured_factories(self, tmp_path: Path):
        components = build_components(load_config(write_config(tmp_path)))

        assert components.request_sources[0].source_kind == "email_inbox"
        assert components.clock.now().isoformat() == "2026-11-01T12:00:00+00:00"

    def test_an_unimportable_factory_is_reported(self, tmp_path: Path):
        config = load_config(
            write_config(tmp_path, email_gateway={"factory": "no.such.module:thing"})
        )
        with pytest.raises(ConfigError, match="cannot import"):
            build_components(config)

    def test_a_missing_factory_attribute_is_reported(self, tmp_path: Path):
        config = load_config(
            write_config(tmp_path, email_gateway={"factory": "recsub.testing.doubles:nope"})
        )
        with pytest.raises(ConfigError, match="no attribute"):
            build_components(config)

    def test_a_component_that_does_not_implement_its_interface_is_rejected(
        self, tmp_path: Path
    ):
        config = load_config(
            write_config(tmp_path, portal_agent={"factory": "recsub.testing.doubles:fixed_clock",
                                                 "options": {"instant": "2026-01-01T00:00:00Z"}})
        )
        with pytest.raises(ConfigError, match="PortalAgent"):
            build_components(config)

    def test_two_sources_may_not_share_a_source_kind(self, tmp_path: Path):
        source = VALID["request_sources"][0]
        config = load_config(write_config(tmp_path, request_sources=[source, source]))
        with pytest.raises(ConfigError, match="source_kind"):
            build_components(config)
