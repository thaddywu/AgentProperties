"""Shared private connection loading and validation; no network or SDK imports."""

from copy import deepcopy
import ipaddress
import json
from pathlib import Path
import re
from urllib.parse import urlsplit


OPENAI_DEFAULTS = dict(
    baseUrl="https://api.openai.com/v1", modelId="gpt-6.1-sol", reasoningEffort="medium"
)
LOCAL_PROVIDER = "codex-compatible-local-endpoint"
AUTO_PROVIDERS = ("openai", "anthropic")
PROVIDERS = {
    "openai": dict(OPENAI_DEFAULTS, protocol="chat-completions"),
    "anthropic": dict(baseUrl="https://api.anthropic.com/v1", modelId="claude-opus-5-5",
                      reasoningEffort="medium", protocol="messages"),
    LOCAL_PROVIDER: dict(protocol="chat-completions"),
}
CONNECTION_FIELDS = {
    "protocol", "baseUrl", "modelId", "apiKey", "reasoningEffort", "maxTokens",
    "timeoutSeconds", "headers", "codingCommand", "responseFormat",
}
CONNECTION_FILENAMES = {
    stem + suffix for stem in ("connection", "connections")
    for suffix in (".yaml", ".yml", ".json")
}


def _unique_mapping(pairs):
    result = {}
    for key, value in pairs:
        if not isinstance(key, str) or key in result:
            raise ValueError("Connection mappings require unique string keys.")
        result[key] = value
    return result


def _yaml_document(text):
    import yaml

    class Loader(yaml.SafeLoader):
        depth = 0

        def compose_node(self, parent, index):
            # Configuration does not need aliases, recursive graphs or merge keys.
            if self.check_event(yaml.AliasEvent) or self.depth >= 32:
                raise ValueError("Connection YAML aliases or excessive nesting are unsupported.")
            self.depth += 1
            try:
                return super().compose_node(parent, index)
            finally:
                self.depth -= 1

        def construct_mapping(self, node, deep=False):
            return _unique_mapping((self.construct_object(key, deep=deep),
                                    self.construct_object(value, deep=deep))
                                   for key, value in node.value)

    try:
        return yaml.load(text, Loader=Loader)
    except (yaml.YAMLError, ValueError, RecursionError):
        # Parser exceptions can include the offending source line and its key.
        raise ValueError("Invalid connection YAML; use unique keys and plain data without aliases.") from None


def load_connection(path):
    """Select one configured section once, then discard all inactive credentials."""
    path = Path(path)
    if path.suffix.lower() not in {".yaml", ".yml"}:
        raise ValueError("Connection file must use .yaml or .yml.")
    with path.open("rb") as stream:
        raw = stream.read(65_537)
    if len(raw) > 65_536:
        raise ValueError("Connection file exceeds 64 KiB.")
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        raise ValueError("Connection file must use UTF-8.") from None
    value = _yaml_document(text)
    if not isinstance(value, dict):
        raise ValueError("Connection file must contain a mapping.")
    if set(value) - {*PROVIDERS, "provider"}:
        raise ValueError("Use only provider and supported connection sections: " + ", ".join(PROVIDERS) + ".")
    sections = {}
    for name in PROVIDERS:
        section = value.get(name)
        if section is None:
            section = {}
        if not isinstance(section, dict) or set(section) - CONNECTION_FIELDS:
            raise ValueError("Provider section must contain supported connection fields.")
        if "apiKey" in section and section["apiKey"] is None:
            section["apiKey"] = ""
        _check_key(section)
        if "protocol" in section and section["protocol"] != PROVIDERS[name]["protocol"]:
            raise ValueError("Provider section uses an incompatible protocol.")
        sections[name] = section
    selected = value.get("provider", "auto")
    if not isinstance(selected, str) or selected not in {*PROVIDERS, "auto"}:
        raise ValueError("provider must be auto or one of: " + ", ".join(PROVIDERS) + ".")
    if selected == "auto":
        selected = next((name for name in AUTO_PROVIDERS if sections[name].get("apiKey", "").strip()), None)
        if selected is None:
            raise ValueError("Fill apiKey in the openai or anthropic section, or explicitly select " + LOCAL_PROVIDER + ".")
    section = sections[selected]
    if not section.get("apiKey", "").strip() and not section.get("baseUrl"):
        raise ValueError("Selected provider requires apiKey, or an explicit endpoint for a keyless connection.")
    settings = dict(PROVIDERS[selected], **section)
    _check_key(settings)
    if "apiKey" in settings:
        settings["apiKey"] = settings["apiKey"].strip()
    validate_settings(settings)
    return settings


def _check_key(settings):
    key = settings.get("apiKey", "")
    if not isinstance(key, str) or any(c in key for c in "\r\n"):
        raise ValueError("Invalid model credential.")


def validate_settings(value):
    if not isinstance(value, dict):
        raise ValueError("Model connection must be a mapping.")
    settings = deepcopy(value)
    protocol = settings.setdefault("protocol", "chat-completions")
    if not isinstance(protocol, str) or protocol not in {"chat-completions", "messages"}:
        raise ValueError("Model protocol must be chat-completions or messages.")
    base = settings.get("baseUrl")
    if not isinstance(base, str):
        raise ValueError("Model connection requires baseUrl.")
    try:
        parsed = urlsplit(base)
        parsed.port
        try:
            loopback = ipaddress.ip_address(parsed.hostname or "").is_loopback
        except ValueError:
            loopback = parsed.hostname == "localhost"
        valid = (parsed.hostname and not parsed.username and not parsed.password
                 and not parsed.query and not parsed.fragment
                 and (parsed.scheme == "https" or parsed.scheme == "http" and loopback)
                 and not any(c.isspace() for c in base))
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Model baseUrl must use HTTPS, or HTTP on loopback.")
    settings["baseUrl"] = base.rstrip("/")
    model = settings.get("modelId")
    if not isinstance(model, str) or not model.strip() or model.startswith("-"):
        raise ValueError("Model connection requires modelId.")
    key = settings.get("apiKey", "")
    if not isinstance(key, str) or any(c in key for c in "\r\n"):
        raise ValueError("Invalid model credential.")
    tokens = settings.setdefault("maxTokens", 12000)
    if type(tokens) is not int or not 1 <= tokens <= 32000:
        raise ValueError("Invalid model token budget.")
    timeout = settings.setdefault("timeoutSeconds", 180)
    if type(timeout) is not int or not 1 <= timeout <= 600:
        raise ValueError("Model timeout must be 1–600 seconds.")
    effort = settings.get("reasoningEffort")
    efforts = {"low", "medium", "high", "xhigh", "max"}
    if protocol == "chat-completions":
        efforts |= {"none", "minimal"}
    if effort is not None and (not isinstance(effort, str) or effort not in efforts):
        raise ValueError("Invalid optional reasoning effort for this protocol.")
    response_format = settings.get("responseFormat")
    if response_format is not None and (
        not isinstance(response_format, dict)
        or response_format.get("type") not in {"json_object", "json_schema"}
        or len(json.dumps(response_format, allow_nan=False)) > 50000
        or response_format.get("type") == "json_schema" and (
            not isinstance(response_format.get("json_schema"), dict)
            or not isinstance(response_format["json_schema"].get("schema"), dict)
        )
    ):
        raise ValueError("Invalid standard structured-response format.")
    headers = settings.setdefault("headers", {})
    if not isinstance(headers, dict) or any(
        not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9-]+", name)
        or name.lower() in {"host", "content-length", "connection", "authorization",
                           "proxy-authorization", "x-api-key", "transfer-encoding"}
        or not isinstance(content, str) or any(c in content for c in "\r\n")
        for name, content in headers.items()
    ):
        raise ValueError("Invalid model connection headers.")
    command = settings.get("codingCommand")
    if command is not None and (not isinstance(command, str) or not command.strip() or "\x00" in command):
        raise ValueError("codingCommand must name one installed executable.")
    return settings


def request_headers(settings, protocol):
    headers = {name.lower(): value for name, value in settings.get("headers", {}).items()}
    headers["content-type"] = "application/json"
    if protocol == "messages":
        headers.setdefault("anthropic-version", "2023-06-01")
        if settings.get("apiKey"):
            headers["x-api-key"] = settings["apiKey"]
    elif settings.get("apiKey"):
        headers["authorization"] = "Bearer " + settings["apiKey"]
    return headers
