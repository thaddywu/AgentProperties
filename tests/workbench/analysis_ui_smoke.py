"""Read-only timeline journey: directed messages, tools, filtering and safe import."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from playwright.sync_api import sync_playwright, expect
from policyscope._paths import cache_directory
from policyscope.workbench.analysis import AnalysisServer


def main():
    example = json.loads((ROOT / "examples/trajectories/team-review.json").read_text())

    def model(stage, prompt):
        payload = json.loads(prompt)
        return (
            json.dumps(dict(unsupported="A finite log cannot prove future behavior."))
            if payload["question"] == "future"
            else json.dumps(
                dict(
                    query="?- Recipient(E,R).",
                    explanation="List the recorded recipients.",
                )
            )
        )

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
            expect(page.locator(".event")).to_have_count(6)
            expect(page.locator(".inspector .content")).to_have_text(
                example["events"][0]["content"]
            )
            expect(page.locator(".inspector")).to_contain_text("Master → Professor")
            expect(
                page.locator("[contenteditable], [name=recipient], #send-message")
            ).to_have_count(0)
            page.get_by_role(
                "button", name="Filter participant Master", exact=True
            ).click()
            expect(page.locator(".event")).to_have_count(3)
            page.get_by_role(
                "button", name="Filter participant All participants", exact=True
            ).click()
            page.get_by_label("Kind", exact=True).select_option("tool_call")
            expect(page.locator(".event")).to_have_count(1)
            expect(page.locator(".inspector")).to_contain_text("dispatch_job")
            page.get_by_role("button", name="Jump to result", exact=True).click()
            expect(page.locator(".event")).to_have_count(6)
            expect(page.locator(".inspector details[open] pre")).to_contain_text(
                "PRIORITY_CONFLICT"
            )
            page.get_by_text("Time range", exact=True).click()
            page.get_by_label("From (UTC)", exact=True).fill("2026-11-13T09:00:06")
            page.get_by_label("Until (UTC)", exact=True).fill("2026-11-13T09:00:07")
            expect(page.locator(".event")).to_have_count(3)
            page.get_by_label("From (UTC)", exact=True).fill("")
            page.get_by_label("Until (UTC)", exact=True).fill("")
            page.locator("#position").focus()
            page.locator("#position").press("Home")
            expect(page.locator(".inspector .content")).to_have_text(
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
            expect(page.locator("h1")).to_have_text("Literal log")
            expect(page.locator(".inspector .content")).to_have_text(
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
            expect(page.locator("h1")).to_have_text("Literal log")
            page.locator("#file").set_input_files(
                dict(
                    name="example.json",
                    mimeType="application/json",
                    buffer=json.dumps(example).encode(),
                )
            )
            expect(page.locator("h1")).to_have_text(example["title"])
            page.get_by_role(
                "button", name="Event 3 Policy gate Decision", exact=True
            ).click()
            expect(page.locator(".inspector details[open] pre")).to_contain_text(
                "Waiting"
            )
            screenshots = cache_directory() / "test-results"
            screenshots.mkdir(parents=True, exist_ok=True)
            page.screenshot(
                path=str(screenshots / "trajectory-viewer.png"), full_page=True
            )
            page.locator("#analysis-tools > summary").click()
            page.get_by_label("Question", exact=True).fill("Who received messages?")
            page.get_by_role("button", name="Ask", exact=True).click()
            expect(page.locator("#query-answer")).to_contain_text("4 matching rows.")
            expect(page.locator("#query-answer")).to_contain_text("?- Recipient(E,R).")
            page.screenshot(
                path=str(screenshots / "trajectory-query.png"), full_page=True
            )
            page.get_by_label("Question", exact=True).fill("future")
            page.get_by_role("button", name="Ask", exact=True).click()
            expect(page.locator("#query-answer")).to_contain_text(
                "cannot prove future behavior"
            )
            exported = page.request.get(base + "/api/analysis/export").json()
            assert exported == example
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
        "Directed messages, tool links, time filtering, safe imports and unchanged export passed without a model or app runner."
    )


if __name__ == "__main__":
    main()
