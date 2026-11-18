"""Source-order review units, separate from model claims and atomic requirements."""

import re


def review_units(review):
    """Pin literal sentence spans; never infer finer semantic correspondence.

    Headings remain visible as context. Every non-heading line is retained,
    including text omitted by the translator. Offsets are Unicode code points.
    This is navigation segmentation, not adjudicated requirement decomposition.
    """
    source = review["source"]["text"]
    units = []
    for line in re.finditer(r"[^\r\n]+", source):
        if re.match(r"\s*#{1,6}\s", line[0]) or not line[0].strip():
            continue
        start = line.start()
        for boundary in re.finditer(r"(?<=[.!?])\s+|(?<=[。！？])", line[0]):
            end = line.start() + boundary.start()
            units.append((start, end))
            start = line.start() + boundary.end()
        units.append((start, line.end()))
    rows = []
    for start, end in units:
        while start < end and source[start].isspace():
            start += 1
        while end > start and source[end - 1].isspace():
            end -= 1
        if start == end:
            continue
        requirements = [
            r for r in review["requirements"] if r["start"] < end and r["end"] > start
        ]
        ids = {r["id"] for r in requirements}
        rows.append(
            dict(
                id=f"sentence:{start}:{end}",
                start=start,
                end=end,
                quote=source[start:end],
                requirementIds=sorted(ids),
                behaviorIds=[
                    b["id"]
                    for b in review["behaviors"]
                    if ids.intersection(b["requirementIds"])
                ],
                mapping="broader"
                if any(r["start"] < start or r["end"] > end for r in requirements)
                else "direct",
                obligations=[
                    dict(id=r["id"], statement=r["statement"])
                    for r in requirements
                    if r["start"] >= start and r["end"] <= end
                ],
            )
        )
    execution = review.get("execution")
    if execution:
        links = {
            link["sentenceId"]: link["procedureIds"] for link in execution["links"]
        }
        known = {p["id"] for p in execution["procedures"]}
        if set(links) != {row["id"] for row in rows} or any(
            not set(ids) <= known for ids in links.values()
        ):
            raise ValueError("Execution alignment does not match source sentences.")
        for row in rows:
            row["procedureIds"] = links[row["id"]]
            row["mapping"] = "model-aligned"
    return dict(method="source-sentences-v1", units=rows)
