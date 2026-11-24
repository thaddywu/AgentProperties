"""Read-only timeline journey: directed messages, tools, filtering and safe import."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import threading
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from playwright.sync_api import sync_playwright, expect
from policyweave._paths import cache_directory
from policyweave.workbench.analysis import AnalysisServer
from policyweave.analysis.log_query import project
from policyweave.analysis.timeline import Timeline


def main():
    screenshots = cache_directory() / "test-results"
    screenshots.mkdir(parents=True, exist_ok=True)
    example = json.loads((ROOT / "examples/trajectories/team-review.json").read_text())
    example["events"][0]["data"] = dict(phase="sent")

    example["analysis"] = project(Timeline(example))

    model_stages = []

    def model(stage, prompt):
        payload = json.loads(prompt.split("\nRepair this candidate:", 1)[0])
        model_stages.append(stage)
        if stage == "call-analysis-queries":
            return json.dumps(dict(queries=[dict(
                query='?- Request(Q,Actor,Action), Parameter(Q,"document",Document), Owns(Owner,Document).',
                explanation="Recorded document ownership.", displayColumns=["Actor", "Document", "Owner"],
            )]))
        if stage == "call-analysis-answer":
            if model_stages.count(stage) == 1:
                return '{"answer":"Synthetic incomplete answer without event citations."}'
            return json.dumps(
                dict(
                    answer=("This call was blocked because the caller does not own the document; the app did not run the operation."
                            if not payload["evidence"]["recordedDecision"]["allowed"]
                            else "The caller owns the document, so this call was allowed and the app ran the operation."),
                    eventIds=[payload["selectedEventId"]],
                    limitations=[],
                )
            )
        raise AssertionError("Only fixed-question evidence queries and explanations are allowed.")

    server = AnalysisServer(("127.0.0.1", 0), example, model)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport=dict(width=1420, height=1040))
            errors, requests = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: requests.append(request.url))
            page.goto(base, wait_until="networkidle")
            page.evaluate("document.fonts.ready")
            assert page.evaluate("document.fonts.check('12px \"Geist Variable\"')")
            assert "Geist Variable" in page.locator("body").evaluate(
                "el => getComputedStyle(el).fontFamily"
            )
            assert page.evaluate(
                'Array.from(document.fonts).some(f => f.family === "Geist Variable" && f.status === "loaded")'
            )
            font_response = page.request.get(base + "/geist-latin-wght-normal.woff2")
            assert font_response.status == 200 and font_response.body()[:4] == b"wOF2"
            expect(page.locator(".event")).to_have_count(4)
            expect(page.locator("#detail .content")).to_have_text(
                example["events"][0]["content"]
            )
            expect(page.locator(".inspector")).to_contain_text("Master → Professor")
            expect(page.locator("#detail")).not_to_contain_text("UTC")
            expect(page.locator("#detail")).not_to_contain_text("Delivery")
            expect(page.locator("time")).to_have_count(0)
            expect(page.locator("#selected-reference")).to_have_count(0)
            expect(page.locator(".event").first.locator(".event-path .badge")).to_have_text("Message send")
            expect(
                page.locator("[contenteditable], [name=recipient], #send-message")
            ).to_have_count(0)
            page.get_by_role(
                "button", name="Filter agent Master", exact=True
            ).click()
            expect(page.locator(".event")).to_have_count(3)
            page.get_by_role(
                "button", name="Filter agent All agents", exact=True
            ).click()
            page.get_by_label("Kind", exact=True).select_option("tool_call")
            expect(page.locator(".event")).to_have_count(1)
            expect(page.locator(".inspector")).to_contain_text("dispatch_job")
            expect(page.get_by_role("button", name="Jump to result", exact=True)).to_have_count(0)
            expect(page.locator("#detail summary")).to_have_text("Result")
            expect(page.get_by_text("PRIORITY_CONFLICT", exact=True)).not_to_be_visible()
            page.locator("#detail summary").click()
            expect(page.locator("#detail")).to_contain_text("PRIORITY_CONFLICT")
            expect(page.locator(".event")).to_have_count(1)
            page.screenshot(
                path=str(screenshots / "trajectory-tool-call.png"), full_page=True
            )
            expect(page.locator("#time-filter, #title, #count, .scope")).to_have_count(
                0
            )
            page.get_by_role("button", name="Open", exact=True).click()
            expect(page.get_by_role("dialog")).to_be_visible()
            expect(page.get_by_role("group", name="Server logs")).to_contain_text(
                example["title"]
            )
            page.get_by_role("button", name=example["title"], exact=True).click()
            expect(page.get_by_role("dialog")).not_to_be_visible()
            expect(page.locator(".event")).to_have_count(4)
            page.locator("#position").focus()
            page.locator("#position").press("Home")
            expect(page.locator("#detail .content")).to_have_text(
                example["events"][0]["content"]
            )
            literal = deepcopy(example)
            literal["title"] = "Literal log"
            literal["events"][0]["content"] = (
                '<img src="https://example.invalid/x" onerror="window.__xss=true">'
            )
            page.locator("#file").set_input_files(
                dict(
                    name="literal.json",
                    mimeType="application/json",
                    buffer=json.dumps(literal).encode(),
                )
            )
            expect(page.locator("#detail .content")).to_have_text(
                literal["events"][0]["content"]
            )
            expect(page.locator(".inspector img")).to_have_count(0)
            assert page.evaluate("window.__xss") is None
            page.locator("#file").set_input_files(
                dict(
                    name="invalid.json",
                    mimeType="application/json",
                    buffer=b'{"format":"unknown"}',
                )
            )
            expect(page.locator("#status")).to_contain_text(
                "selected log was preserved"
            )
            page.locator("#file").set_input_files(
                dict(
                    name="example.json",
                    mimeType="application/json",
                    buffer=json.dumps(example).encode(),
                )
            )
            page.get_by_label("All events", exact=True).check()
            page.get_by_role(
                "button", name="Event 3 Policy gate Event", exact=True
            ).click()
            expect(page.locator("#detail")).to_contain_text("PRIORITY_CONFLICT")
            page.screenshot(
                path=str(screenshots / "trajectory-viewer.png"), full_page=True
            )
            page.get_by_role("tab", name="QA", exact=True).click()
            expect(
                page.locator(
                    "#advanced-analysis, #query-form, #template-form, #ask-form"
                )
            ).to_have_count(0)
            exported = page.request.get(base + "/api/analysis/export").json()
            assert exported == example
            page.get_by_role("tab", name="Evidence", exact=True).click()
            expect(page.locator("#fact-status")).to_have_text("No database was recorded for this event.")
            expect(page.locator("#facts")).to_be_empty()
            for label in ("Rules", "Log facts"):
                expect(page.get_by_role("tab", name=label, exact=True)).to_have_count(0)
            expect(page.locator("#snapshot-scope, #fact-search, #derive")).to_have_count(0)
            model_log = deepcopy(example)
            model_log.pop("analysis", None)
            model_log["roles"] = [dict(id="master", name="Runner", kind="agent"),
                                  dict(id="observer", name="Background observer", kind="observer")]
            model_log["events"] = [
                dict(id="request", sequence=0, kind="llm_call", actor="master", callId="model",
                     arguments=dict(messages=[dict(role="user", content="INTERNAL_INPUT_MARKER")])),
                dict(id="response", sequence=1, kind="llm_result", actor="master", callId="model",
                     result=dict(summary="Request review before dispatch.", tool="send_message")),
                dict(id="background", sequence=2, kind="tool_call", actor="observer", callId="background-call", tool="poll", arguments={}),
            ]
            page.locator("#file").set_input_files(dict(name="model.json", mimeType="application/json", buffer=json.dumps(model_log).encode()))
            expect(page.locator(".event")).to_have_count(1)
            expect(page.locator(".event")).to_have_attribute("data-event-id", "response")
            expect(page.locator("#detail")).to_contain_text("Request review before dispatch.")
            expect(page.locator("#detail")).not_to_contain_text("INTERNAL_INPUT_MARKER")
            expect(page.locator("#detail")).not_to_contain_text("Model input")
            expect(page.get_by_role("button", name="Filter agent Runner", exact=True)).to_be_visible()
            expect(page.get_by_role("button", name="Filter participant Background observer", exact=True)).to_have_count(0)
            page.get_by_label("All events", exact=True).check()
            expect(page.get_by_role("button", name="Filter participant Background observer", exact=True)).to_be_visible()
            assert page.request.get(base + "/api/analysis/export").json() == model_log
            # The shared JSONL importer needs no app-specific converter.
            model_log["events"] = [dict(id="output", sequence=0, kind="llm_output", actor="master", result="Visible output only.")]
            header = {key: item for key, item in model_log.items() if key != "events"}
            text = "\n".join(json.dumps(row) for row in [header, *model_log["events"]]) + "\n"
            page.locator("#file").set_input_files(dict(name="model.jsonl", mimeType="application/x-ndjson", buffer=text.encode()))
            expect(page.locator("#detail")).to_contain_text("Visible output only.")
            expect(page.locator(".event")).to_have_count(1)
            # Real captured policy snapshots: typed EDB/IDB, explicit phase, and unchanged export.
            from policyweave.enforcement import Policy, record_execution

            with tempfile.TemporaryDirectory() as directory:
                policy_path = Path(directory) / "rules.dl"
                policy_path.write_text(
                    ".decl Owns(Actor:symbol, Document:symbol)\n.input Owns\n"
                    ".decl CanRead(Actor:symbol, Document:symbol)\n"
                    'Owns("alice","doc-1").\n'
                    "CanRead(A,D) :- Owns(A,D).\n"
                    'Allow(Q) :- Request(Q,A,"read_document"), Parameter(Q,"document",D), CanRead(A,D).\n'
                    'Deny(Q,"not_owner") :- Request(Q,A,"read_document"), Parameter(Q,"document",D), not CanRead(A,D).\n'
                )
                policy = Policy(policy_path, trace=True)
                try:
                    with record_execution("Monitored tool calls") as recording:
                        policy.call(
                            "alice",
                            "read_document",
                            {"document": "doc-1"},
                            lambda: {"status": "AVAILABLE", "title": "Synthetic document"},
                        )
                        policy.call(
                            "bob",
                            "read_document",
                            {"document": "doc-1"},
                            lambda: (_ for _ in ()).throw(AssertionError("Blocked effect")),
                        )
                    captured = policy.trajectory()
                    monitored = recording.export()
                finally:
                    policy.runtime.close()
            page.locator("#file").set_input_files(
                dict(
                    name="gate.json",
                    mimeType="application/json",
                    buffer=json.dumps(captured).encode(),
                )
            )
            expect(page.locator(".event")).to_have_count(2)
            expect(page.locator(".event .badge.applied")).to_have_text("Checked")
            page.locator(".event").first.click()
            expect(page.locator("#detail .call-outcome .badge")).to_have_text("Checked")
            page.locator(".event").last.click()
            expect(page.locator("#detail")).to_contain_text("not_owner")
            expect(page.locator("#detail .call-outcome .badge")).to_have_text("Blocked")
            expect(page.locator("#detail .outcome")).to_have_count(0)
            assert page.request.get(base + "/api/analysis/export").json() == captured
            # A normal monitor export resolves its own gate by call ID, without host sidecar links.
            page.locator("#file").set_input_files(dict(name="monitored.json", mimeType="application/json", buffer=json.dumps(monitored).encode()))
            expect(page.locator(".event")).to_have_count(2)
            expect(page.locator(".event .badge.blocked")).to_have_count(1)
            expect(page.locator(".event .badge.applied")).to_have_count(1)
            expect(page.locator("#detail .call-outcome .badge")).to_have_text("Blocked")
            expect(page.locator("#detail")).to_contain_text("doc-1")
            expect(page.locator("#detail")).to_contain_text("not_owner")
            page.get_by_role("tab", name="Evidence", exact=True).click()
            expect(page.get_by_role("heading", name="Database", exact=True)).to_be_visible()
            expect(page.get_by_role("tab", name="EDB", exact=True)).to_have_count(0)
            expect(page.get_by_role("tab", name="IDB", exact=True)).to_have_count(0)
            expect(page.locator("#snapshot-scope, #fact-search, #derive, #rules-panel")).to_have_count(0)
            expect(page.locator('#facts [data-predicate="Request"]')).to_contain_text(
                "bob"
            )
            expect(page.locator('#facts [data-predicate="Deny"]')).to_contain_text(
                "not_owner"
            )
            expect(page.locator('#facts [data-predicate="Parameter"]')).to_contain_text("doc-1")
            expect(page.locator("#fact-status")).to_be_empty()
            expect(page.locator("#evidence-panel")).not_to_contain_text("Gate snapshot")
            expect(page.locator("#evidence-panel")).not_to_contain_text("Recorded at this decision")
            page.screenshot(
                path=str(screenshots / "trajectory-database.png"), full_page=True
            )
            page.get_by_role("button", name="Toggle theme", exact=True).click()
            expect(page.locator("html")).to_have_attribute("data-theme", "dark")
            page.screenshot(
                path=str(screenshots / "trajectory-database-dark.png"), full_page=True
            )
            page.get_by_role("button", name="Toggle theme", exact=True).click()
            page.get_by_role("button", name="After", exact=True).click()
            expect(page.locator("#fact-status")).to_be_empty()
            expect(page.locator('#facts [data-predicate="Deny"]')).to_contain_text(
                "Not recorded"
            )
            page.get_by_role("tab", name="QA", exact=True).click()
            expect(page.locator('#analysis-tools textarea, #analysis-tools input, [contenteditable]')).to_have_count(0)
            expect(page.locator('#call-suggestions button')).to_have_count(4)
            for call_index, allowed in ((1, False), (0, True)):
                page.locator(".event").nth(call_index).click()
                why = "Why allowed?" if allowed else "Why blocked?"
                expect(page.get_by_role("button", name=why, exact=True)).to_be_visible()
                for label, preset in ((why, "decision"), ("Access control", "conditions"),
                                      ("Information flow", "flow"), ("Effects", "effect")):
                    page.get_by_role("button", name=label, exact=True).click()
                    expect(page.get_by_role("button", name=label, exact=True)).to_have_attribute("aria-pressed", "true")
                    expect(page.locator("#call-answer")).to_be_empty()
                    page.get_by_role("button", name="Analysis", exact=True).click()
                    expect(page.locator("#call-answer .analysis-answer")).to_contain_text(
                        "app ran the operation" if allowed else "app did not run the operation")
                    expect(page.locator("#call-answer > .query-results")).to_have_count(2)
                    if preset in {"decision", "conditions"}:
                        expect(page.locator("#call-answer .query-results").nth(1)).to_contain_text("alice")
                        expect(page.locator("#call-answer .query-results").nth(1)).to_contain_text("doc-1")
                    if preset == "flow":
                        expect(page.locator("#call-answer")).to_contain_text("No source or dependency facts were recorded")
                    if preset == "effect":
                        expect(page.locator("#call-answer summary").filter(has_text="Recorded effects")).to_be_visible()
                        expect(page.locator("#call-answer")).to_contain_text("Operation started")
                        expect(page.locator("#call-answer")).to_contain_text("AVAILABLE" if allowed else "UNAVAILABLE")
                    page.get_by_text("Translation and query", exact=True).click()
                    expect(page.locator("#call-answer")).to_contain_text("Decision replay matched.")
                    if preset in {"decision", "conditions"}:
                        expect(page.locator("#call-answer pre").last).to_contain_text("Owns")
                    if not allowed:
                        page.screenshot(path=str(screenshots / f"trajectory-call-{preset}.png"), full_page=True)
                        if preset == "decision":
                            assert model_stages.count("call-analysis-queries") == 1
                            assert model_stages.count("call-analysis-answer") == 2
                            page.screenshot(path=str(screenshots / "trajectory-answer-repaired.png"), full_page=True)
            assert model_stages.count("call-analysis-queries") == 4
            assert model_stages.count("call-analysis-answer") == 9
            assert "analysis-query" not in model_stages
            assert page.request.get(base + "/api/analysis/export").json() == monitored
            page.set_viewport_size(dict(width=390, height=844))
            page.get_by_role("tab", name="Details", exact=True).click()
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
            ), "Mobile horizontal overflow"
            assert not errors, errors
            assert all(url.startswith(base + "/") or url == base for url in requests), (
                requests
            )
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    print(
        "Directed messages, tool links, server log selection, safe imports and unchanged export passed without a model or app runner."
    )


if __name__ == "__main__":
    main()
