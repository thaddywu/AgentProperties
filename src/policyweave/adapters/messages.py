"""Native Messages wire translation for bounded, data-only model calls."""

from copy import deepcopy
import json


def structured_schema(schema):
    """Reduce unsupported wire constraints; host stage validators retain limits.

    Bounds are kept as model instructions. This is a transport projection, never
    a replacement for validating the original inventory/binding/reading contract.
    """
    result = deepcopy(schema)
    bounds = {}
    for key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
                "multipleOf", "minLength", "maxLength", "maxItems", "uniqueItems"):
        if key in result:
            bounds[key] = result.pop(key)
    if result.get("minItems", 0) not in {0, 1}:
        bounds["minItems"] = result["minItems"]
        result["minItems"] = 1
    if bounds:
        result["description"] = (result.get("description", "") +
                                 " Required constraints: " + json.dumps(bounds)).strip()
    for key in ("properties", "$defs", "definitions"):
        if key in result:
            result[key] = {name: structured_schema(value) for name, value in result[key].items()}
    for key in ("items",):
        if isinstance(result.get(key), dict):
            result[key] = structured_schema(result[key])
    for key in ("anyOf", "allOf", "oneOf"):
        if key in result:
            result[key] = [structured_schema(value) for value in result[key]]
    return result


def payload_for_messages(model, tokens, instructions, prompt, effort, response_format):
    payload = dict(model=model, max_tokens=tokens, system=instructions,
                   messages=[dict(role="user", content=prompt)])
    config = {}
    if effort is not None:
        config["effort"] = effort
    if response_format and response_format["type"] == "json_schema":
        config["format"] = dict(type="json_schema", schema=structured_schema(
            response_format["json_schema"]["schema"]
        ))
    if config:
        payload["output_config"] = config
    if response_format and response_format["type"] == "json_object":
        payload["system"] += " Return exactly one JSON object."
    return payload


def read_message(data):
    if data.get("type") != "message" or data.get("stop_reason") != "end_turn":
        raise ValueError("Model response is incomplete or refused.")
    pieces = []
    for block in data["content"]:
        kind = block.get("type")
        if kind == "text" and isinstance(block.get("text"), str):
            pieces.append(block["text"])
        elif kind not in {"thinking", "redacted_thinking"}:
            raise ValueError("Unexpected model response block.")
    text = "".join(pieces)
    if not text.strip():
        raise ValueError("Model response contains no text.")
    usage = data.get("usage", {})
    mapped = {}
    for source, target in (("input_tokens", "prompt_tokens"),
                           ("output_tokens", "completion_tokens")):
        if type(usage.get(source)) is int:
            mapped[target] = usage[source]
    if "prompt_tokens" in mapped:
        mapped["prompt_tokens"] += sum(
            usage[key] for key in ("cache_creation_input_tokens", "cache_read_input_tokens")
            if type(usage.get(key)) is int
        )
    if len(mapped) == 2:
        mapped["total_tokens"] = sum(mapped.values())
    return text, mapped
