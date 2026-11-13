"""Shared bounded model-output parsing and review vocabulary."""

import json
import re

IMPLEMENTATIONS = ("datalog", "mechanism", "adapter", "unsupported", "ambiguous")
CATEGORIES = ("permission", "information_flow", "lifecycle", "other", "uncertain")
RELATIONS = ("equivalent", "stronger", "weaker", "partial", "unresolved")
ID = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{0,63}")


def bounded(value, limit=8000):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit


def strings(value, limit=100):
    return (
        isinstance(value, list)
        and len(value) <= limit
        and all(bounded(x, 4000) for x in value)
    )


def parse_json(raw):
    if not isinstance(raw, str) or len(raw) > 200_000:
        raise ValueError("Model response exceeds the size limit.")
    value = json.loads(
        re.sub(r"^```(?:json)?\s*\n([\s\S]*?)\n```$", r"\1", raw.strip())
    )
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object.")
    return value


def checked(stage, payload, validate, generate, record):
    prompt = json.dumps(payload, ensure_ascii=False)
    for attempt in range(3):
        raw = generate(stage, prompt)
        entry = dict(stage=stage, attempt=attempt + 1, prompt=prompt, response=raw)
        try:
            result = validate(parse_json(raw))
        except (ValueError, KeyError, TypeError) as error:
            entry["error"] = str(error)
            record(entry)
            if attempt == 2:
                raise ValueError(f"{stage} failed structural validation") from error
            prompt = (
                json.dumps(payload, ensure_ascii=False)
                + "\nRepair this candidate: "
                + json.dumps(dict(error=str(error), candidate=raw))
            )
        else:
            record(entry)
            return result
