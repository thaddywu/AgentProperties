"""Read-only execution descriptions, followed by a separate source-alignment pass.

Descriptions are model interpretations, never executable policy or approval.
Only structural coverage and evidence quotations are checked automatically.
"""

from policyweave.core.datalog import parse, variable, decode

SOURCES = {
    "runtime identity",
    "tool call",
    "application state",
    "tool result",
    "agent statement",
    "static configuration",
    "rule constant",
    "unknown",
}

# Shared by reconstruction and presentation in both model adapters.
REQUIREMENT_STYLE = (
    "Explain ONLY the added enforcement for an application author reviewing policy fidelity. "
    "One check is one independently reviewable requirement. Separate role permissions, each role's "
    "resource limits, physical capacity, ownership, approval validity, scheduling and completion evidence. "
    "Separate approval permission from rejection permission, and starting permission from current "
    "approval. Never collect all checks of submit/revise/finish or all permissions of a role in one "
    "record. Related actions may share one requirement when the actual condition is shared. "
    "Refer to other checks without repeating their conditions or thresholds. Group roles only when "
    "their requirement and actual check are the same. Rule IDs may support multiple requirements. "
)

READING_STYLE = REQUIREMENT_STYLE + (
    "Write a succinct executable explanation in two parts: recorded facts, then rules and refusal. "
    "Use a short concrete title, such as Approval before dispatch. "
    "The summary starts Records: and names the actual tool call, the facts read or recorded, and when. "
    "Distinguish request inputs from facts recorded only after confirmed success. "
    "This part contains only call observations and success recording, not audit caveats or history-retention commentary. "
    "The first detail line starts Rules: and explains the actual matching/derivation conditions together "
    "with what is refused when they fail. Use one to three short detail lines. "
    "Those lines describe actual decision conditions and refusal, not extra explanatory appendices. "
    "Prefer a few short sentences, using the space needed for the actual conditions without repetition. "
    "Use short sentences and concrete verbs. Say job ID, current task version, unchanged task details "
    "and exact resource request rather than reciting hashes, canonical tuples or record-type joins. "
    "Titles name the operation or constraint, not vague judgments such as smaller or tighter. "
    "Say all required resource values must meet the limits, not positive envelope. Say the app's "
    "existing resource check, not quota_ok or an internal method name. User-visible tool names are "
    "useful; private callback names and database terminology are not. State a condition once, rather "
    "than repeating it separately as eligibility, derivation and execution. "
    "A small number of actual predicate names may clarify the explanation. The supplied names are "
    "implementation context. Do not invent an intermediate relation to make the explanation shorter, "
    "or describe an IDB conclusion as an inserted input fact. "
    "Do not list every Field tuple or refer to internal check IDs or class/method names. "
    "Check IDs are bookkeeping keys, not declared predicates: never say that a bound or guarantee "
    "comes from one of those IDs. Express the actual shared condition in ordinary words instead. "
    "Keep exact numerical bounds/units, all/any, negation, same-job/run/version matches, success producers "
    "and missing-input behavior. Distinguish explicit Deny from absence of Allow. "
    "Explain the scoped check, not final authorization or business success. Permission for original-app "
    "error handling is not an added refusal. Identify necessary delegated checks without attributing "
    "them to the added rules. Explain a material gap by the concrete action or content left unchecked, "
    "such as message bodies or model contexts; do not hide that limitation in optional content. "
    "Use relevant frozen global limitations to identify actual unprotected channels; do not infer "
    "information-flow protection from role-based read permission or from observing a message. "
    "Retain detailed lifecycle, source-authority and bypass analysis in the frozen evidence. Do not "
    "append generic restart, authentication, physical-proof, expiry or implementation-audit paragraphs. "
    "Do not narrate journal restoration or inventory missing order/expiry comparisons: state the actual "
    "recorded success event required and that missing evidence prevents Allow. "
    "Do not inventory absent comparisons or unrelated quota types. Mention original-app checks only "
    "when they supply a guarantee this description would otherwise attribute to the added layer. "
    "A missing required success event can simply be stated as missing evidence that prevents Allow. "
    "Do not strengthen refusal-if-over-limit into permission-only-if-within-limit when missing inputs "
    "behave differently. Do not fix or extend the implementation. Return examples=[]; the two parts "
    "should be self-contained. Use plain text without Markdown backticks or all-caps emphasis."
)


def validate_execution(value, rules, evidence):
    procedures = value.get("procedures", [])
    if not isinstance(procedures, list) or not 1 <= len(procedures) <= 80:
        raise ValueError("Return 1–80 procedures.")
    ids, covered = set(), set()
    rule_ids = {r["id"] for r in rules}
    for p in procedures:
        if not isinstance(p.get("id"), str) or not p["id"] or p["id"] in ids:
            raise ValueError("Procedure IDs must be unique.")
        ids.add(p["id"])
        if "summary" in p and (
            not isinstance(p["summary"], str) or not 1 <= len(p["summary"]) <= 360
        ):
            raise ValueError("Student summaries require 1–360 characters.")
        if (
            not isinstance(p.get("title"), str)
            or not p["title"]
            or len(p["title"]) > 180
        ):
            raise ValueError("Use a short action title.")
        if not isinstance(p.get("ruleIds"), list) or not set(p["ruleIds"]) <= rule_ids:
            raise ValueError("Unknown rule reference.")
        covered.update(p["ruleIds"])
        for field in ("reads", "steps", "evidence"):
            if not isinstance(p.get(field), list):
                raise ValueError(f"{field} must be an array.")
        if not 1 <= len(p["steps"]) <= 30:
            raise ValueError("Use 1–30 concise execution lines per procedure.")
        for line in p["steps"]:
            if (
                type(line.get("indent")) is not int
                or not 0 <= line["indent"] <= 4
                or not isinstance(line.get("text"), str)
                or not line["text"]
                or len(line["text"]) > 550
                or ("kind" in line and line["kind"] not in {"A", "B", "C"})
            ):
                raise ValueError(
                    "Execution lines need indent 0–4, short text and optional kind A, B or C."
                )
        for read in p["reads"]:
            sources = read.get("sources", [read.get("source")])
            if (
                not isinstance(sources, list)
                or not sources
                or not set(sources) <= SOURCES
                or not isinstance(read.get("text"), str)
                or not read["text"]
                or len(read["text"]) > 550
            ):
                raise ValueError(
                    "Each read needs short text and sources from: "
                    + ", ".join(sorted(SOURCES))
                )
        if not p["evidence"]:
            raise ValueError("Cite implementation evidence for each procedure.")
        citations = []
        for citation in p["evidence"]:
            if (
                citation.get("file") not in evidence
                or not isinstance(citation.get("quote"), str)
                or not citation["quote"].strip()
            ):
                raise ValueError(
                    "Evidence must quote an exact substring of a supplied file."
                )
            source = evidence[citation["file"]]
            if citation["quote"] in source:
                citations.append(citation)
                continue
            # Models sometimes join non-adjacent clauses into one quotation.
            # Accept them only as separate, individually exact source citations.
            lines = [
                line
                for line in citation["quote"].replace("\\n", "\n").splitlines()
                if line.strip()
            ]
            if not lines or any(line not in source for line in lines):
                raise ValueError(
                    f"{p['id']}: quote exact source text from {citation['file']}; do not paraphrase evidence."
                )
            citations.extend(dict(file=citation["file"], quote=line) for line in lines)
        p["evidence"] = citations
    if covered != rule_ids:
        raise ValueError("Missing rule IDs: " + ", ".join(sorted(rule_ids - covered)))
    return procedures


def describe_execution(rules, binding, evidence, generate, record=lambda _: None):
    """Run independent reconstruction and presentation, returning review procedures."""
    from .workflow import execution_workflow

    return execution_workflow(rules, binding, evidence, generate, record)["procedures"]


def split_direct_permissions(procedures, rules, evidence):
    """Keep unrelated simple permissions from sharing one display/mapping target.

    Only the exact Allow(q) :- Request(q, constant actor, constant action) shape
    is rendered here. Other checks stay with the independent model reading.
    """
    by_id = {r["id"]: r for r in rules}
    output = []
    for procedure in procedures:
        direct = []
        for identifier in procedure["ruleIds"]:
            rule = parse(by_id[identifier]["datalog"])[0][0]
            body = rule["body"]
            if (
                rule["head"]["predicate"] != "Allow"
                or len(body) != 1
                or body[0]["predicate"] != "Request"
                or body[0].get("negative")
                or rule["distinct"]
                or rule.get("comparisons")
                or rule["head"]["args"] != body[0]["args"][:1]
                or any(variable(t) for t in body[0]["args"][1:])
            ):
                break
            direct.append((identifier, *map(decode, body[0]["args"][1:])))
        else:
            if len(direct) > 1:
                for identifier, actor, action in direct:
                    quote = by_id[identifier]["datalog"]
                    if quote not in evidence.get("rules.dl", ""):
                        # Keep original, checked citations if serialization differs.
                        citations = procedure["evidence"]
                    else:
                        citations = [dict(file="rules.dl", quote=quote)]
                    output.append(
                        dict(
                            id=procedure["id"] + "_" + identifier,
                            title=f"{actor}: {action}",
                            summary=f"{actor} may request {action}, unless another check refuses it. The original tool's checks still apply.",
                            ruleIds=[identifier],
                            reads=[
                                dict(
                                    text="The bound caller",
                                    sources=["runtime identity"],
                                ),
                                dict(
                                    text="The requested operation",
                                    sources=["tool call"],
                                ),
                            ],
                            steps=[
                                dict(
                                    indent=0,
                                    text=f"{actor} may request {action}, unless another check refuses the call.",
                                ),
                            ],
                            evidence=citations,
                            origin="direct-rule-rendering",
                        )
                    )
                continue
        output.append(procedure)
    # Numeric thresholds are read from the parsed program, not inferred from NL.
    for procedure in output:
        values = []
        for identifier in procedure["ruleIds"]:
            rule = parse(by_id[identifier]["datalog"])[0][0]
            for comparison in rule.get("comparisons", []):
                for side in ("left", "right"):
                    term = comparison[side]
                    if not variable(term) and decode(term) not in values:
                        values.append(decode(term))
        if values:
            text = "Fixed comparison values: " + ", ".join(values)
            if not any(read["text"] == text for read in procedure["reads"]):
                procedure["reads"].append(dict(text=text, sources=["rule constant"]))
    return output
