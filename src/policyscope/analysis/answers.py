"""Deterministic answer templates over exact query rows; no model calls or code."""

import re
from string import Formatter


def fields(text):
    if not isinstance(text, str) or not 1 <= len(text) <= 2000:
        raise ValueError("Answer wording must be bounded text.")
    names = set()
    for _, name, specification, conversion in Formatter().parse(text):
        if name is not None:
            if (
                not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name)
                or specification
                or conversion
            ):
                raise ValueError("Answer placeholders must be plain field names.")
            names.add(name)
    return names


def validate_answer(value, columns):
    if not isinstance(value, dict) or not value or set(value) - {"en", "zh"}:
        raise ValueError("Answer templates support en/zh text variants.")
    for wording in value.values():
        if not isinstance(wording, dict) or set(wording) != {"summary", "row", "empty"}:
            raise ValueError("Answer templates require summary, row and empty text.")
        if fields(wording["summary"]) - {"count"} or fields(wording["empty"]):
            raise ValueError("Invalid answer summary placeholders.")
        if fields(wording["row"]) - set(columns):
            raise ValueError("Answer row refers to a missing query column.")


def render_answer(result, *, template=None, question=""):
    chinese = bool(re.search(r"[\u3400-\u9fff]", question))
    variants = (template or {}).get("answer", {})
    wording = variants.get("zh" if chinese else "en") or next(
        iter(variants.values()), None
    )
    rows = result["rows"]
    if wording:
        summary = (
            wording["summary"].format(count=len(rows)) if rows else wording["empty"]
        )
        items = [
            wording["row"].format_map(dict(zip(result["columns"], row)))
            for row in rows[:20]
        ]
    elif not result["columns"]:
        summary = (
            (
                "该查询在当前证据中成立。"
                if rows
                else "该查询在当前证据中不成立；仅限当前证据。"
            )
            if chinese
            else (
                "The query holds in the supplied evidence."
                if rows
                else "The query does not hold in the supplied evidence."
            )
        )
        items = []
    else:
        summary = (
            (
                f"查询匹配到 {len(rows)} 条记录。"
                if rows
                else "当前证据中没有匹配记录；这不能证明所有政策都已满足。"
            )
            if chinese
            else (
                f"Query matched {len(rows)} records."
                if rows
                else "No matching records in the supplied evidence; this does not establish full-policy satisfaction."
            )
        )
        items = [
            "; ".join(
                f"{name}: {value}" for name, value in zip(result["columnLabels"], row)
            )
            for row in rows[:20]
        ]
    return dict(
        templateId=(template or {}).get("id", "query-rows"),
        summary=summary,
        items=items,
        eventIds=result["eventIds"],
        truncated=len(rows) > 20,
        scope=result["scope"],
        source="deterministic-template",
    )
