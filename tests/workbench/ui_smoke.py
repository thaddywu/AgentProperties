"""Review browser journey with a synthetic model; no hosted services."""

from pathlib import Path
import json
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT / "src",):
    sys.path.insert(0, str(directory))

from playwright.sync_api import sync_playwright, expect
from policyscope.workbench.example import Application
from policyscope.workbench.server import Server
from policyscope.workbench.study import Study


def synthetic_model(stage, prompt):
    payload = json.loads(prompt)
    if stage == "requirements":
        return json.dumps(
            dict(
                requirements=[
                    dict(
                        id="r1",
                        quote=payload["source"],
                        statement="Permit reading.",
                        implementation="datalog",
                        relation="equivalent",
                        categories=["permission"],
                        assumptions=[],
                        predicates=["Request", "Allow"],
                    )
                ]
            )
        )
    if stage == "rules":
        return json.dumps(
            dict(
                rules=[dict(id="read", datalog='Allow(Q) :- Request(Q, A, "read").')],
                coverage=[dict(id="r1", ruleIds=["read"])],
            )
        )
    return json.dumps(
        dict(
            behaviors=[
                dict(
                    id="reading",
                    ruleIds=["read"],
                    summary="Read requests are allowed.",
                    conditions=[],
                )
            ]
        )
    )


def main():
    screenshots = ROOT / "test-results"
    screenshots.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        server = Server(
            ("127.0.0.1", 0), Study(directory, Application()), synthetic_model
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page(
                    viewport=dict(width=1380, height=920), color_scheme="light"
                )
                errors = []
                page.on(
                    "pageerror",
                    lambda e: (errors.append(str(e)), print("Browser error:", str(e))),
                )
                page.goto(f"http://127.0.0.1:{server.server_port}")
                expect(page.locator("nav")).to_have_count(0)
                expect(page.locator("header")).not_to_contain_text("PolicyScope")
                expect(page.get_by_label("Review version")).to_have_count(0)
                expect(
                    page.locator(".policy-column").get_by_role(
                        "group", name="Category", exact=True
                    )
                ).to_be_visible()
                expect(page.locator(".review .statement")).to_have_count(0)
                expect(page.get_by_text("Other execution", exact=False)).to_have_count(
                    0
                )
                expect(page.locator("header")).not_to_contain_text("Document access")
                page.get_by_label("Capability / access control", exact=True).check()
                page.get_by_label("Other", exact=True).check()
                page.get_by_label("Your category").fill("Retention")
                page.get_by_label("Partly matches", exact=True).check()
                page.get_by_label("What is missing or different?").fill(
                    "Missing an exception for shared documents."
                )
                expect(page.locator("#save-status")).to_have_text("Saved")
                page.get_by_role("button", name="Next", exact=True).click()
                expect(page.get_by_label("Policy sentence")).to_have_value("1")
                page.get_by_label("Fully matches", exact=True).check()
                expect(page.locator("#save-status")).to_have_text("Saved")
                page.get_by_role("button", name="Previous", exact=True).click()
                expect(page.get_by_label("Your category")).to_have_value("Retention")
                expect(
                    page.get_by_label("What is missing or different?")
                ).to_have_value("Missing an exception for shared documents.")
                page.reload()
                expect(page.get_by_label("Partly matches", exact=True)).to_be_checked()
                expect(page.get_by_text("Datalog", exact=True)).to_have_count(0)
                expect(
                    page.get_by_text("Conditions & sources", exact=True)
                ).to_have_count(0)
                page.screenshot(path=str(screenshots / "review.png"), full_page=True)
                exported = page.request.get(
                    f"http://127.0.0.1:{server.server_port}/api/export"
                ).json()
                stats = exported["summary"]["reviews"][0]["sentenceReview"]
                assert stats["rated"] == 2 and stats["categories"]["other"] == 1
                page.get_by_role("button", name="Open policy").click()
                document = Path(directory) / "student-policy.txt"
                document.write_text("Permit reading. 😀")
                page.get_by_label("Open policy document").set_input_files(document)
                expect(page.locator("#source")).to_have_value("Permit reading. 😀")
                page.get_by_role("button", name="Translate", exact=True).click()
                expect(page.get_by_text("Read requests are allowed.")).to_be_visible()
                expect(page.get_by_label("Review version")).to_contain_text("Version 2")
                page.reload()
                expect(page.get_by_label("Review version")).to_contain_text("Version 2")
                version = page.get_by_label("Review version")
                version.select_option(exported["study"]["reviews"][0]["id"])
                expect(page.get_by_label("Partly matches", exact=True)).to_be_checked()
                page.get_by_label("Policy sentence").select_option("1")
                expect(
                    page.get_by_role("button", name="Next", exact=True)
                ).to_be_disabled()
                assert not errors, errors
                browser.close()
                print(
                    "Review, sentence autosave, categories under the source, translation, version switching and export passed."
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    main()
