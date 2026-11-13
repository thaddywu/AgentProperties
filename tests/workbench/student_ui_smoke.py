"""Portable review UI: save to review.json and resume with no internal cache."""

import json
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
for directory in ("src",):
    sys.path.insert(0, str(ROOT / directory))

from playwright.sync_api import expect, sync_playwright
from test_student_workflow import StudentWorkflowTests
from policyscope.workbench.server import Server
from policyscope.workbench.student_review import StudentStudy
from policyscope.policy_adder.codex import save


def main():
    fixture = StudentWorkflowTests()
    fixture.setUp()
    try:
        # Keep old verbose titles and unlinked descriptions in the stored bundle;
        # the reviewer should see only relevant business sentences.
        reference_path = fixture.port.output / "review.json"
        reference = json.loads(reference_path.read_text())
        reference["execution"]["procedures"][0]["title"] = (
            "Bind a caller, evaluate current state, and distinguish permission from effect"
        )
        reference["execution"]["procedures"][0]["steps"] = [
            dict(
                kind="A",
                indent=0,
                text="Before approve, the application supplies the caller role.",
            ),
            dict(
                kind="B",
                indent=0,
                text="If the caller is the reviewer, derive permission.",
            ),
            dict(
                kind="C",
                indent=0,
                text="Allow approval when the actor is the reviewer.",
            ),
        ]
        reference["execution"]["procedures"][0]["evidence"] = [
            dict(
                file="source/policy_port/rules.dl",
                quote='Allow(Q) :- Request(Q,"reviewer","approve").',
            )
        ]
        reference["execution"]["procedures"].append(
            dict(
                id="legacy",
                title="Older execution format",
                ruleIds=[],
                reads=[],
                steps=[
                    dict(indent=0, text="An older description without stage labels.")
                ],
                evidence=[],
            )
        )
        reference["execution"]["links"][1]["procedureIds"] = ["legacy"]
        reference["execution"]["procedures"].append(
            dict(
                id="unlinked",
                title="Unrelated execution",
                ruleIds=[],
                reads=[],
                steps=[dict(indent=0, text="An unrelated implementation detail.")],
                evidence=[],
            )
        )
        save(reference_path, reference)
        application = fixture.export()
        path = fixture.target / "review.json"
        path.unlink()  # First launch creates the submission automatically.
        study = StudentStudy(fixture.root / "cache-one", application, path)
        server = Server(("127.0.0.1", 0), study)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            try:
                page.goto(f"http://127.0.0.1:{server.server_port}")
                expect(page.locator("nav")).to_have_count(0)
                expect(page.get_by_label("Review version")).to_have_count(0)
                expect(
                    page.locator(".policy-column").get_by_role(
                        "group", name="Category", exact=True
                    )
                ).to_be_visible()
                expect(page.locator(".review")).not_to_contain_text(
                    "Only the reviewer may approve an operation."
                )
                expect(page.locator(".review")).not_to_contain_text("Bind a caller")
                expect(
                    page.get_by_text("An unrelated implementation detail.")
                ).to_have_count(0)
                expect(page.locator(".execution-caption")).to_have_text(
                    [
                        "Recorded information",
                        "Decision rules",
                        "Before execution",
                    ]
                )
                expect(page.locator(".execution-section").nth(0)).to_contain_text(
                    "Before approve, the application supplies the caller role."
                )
                tool_name = page.locator(".execution-line code")
                expect(tool_name).to_have_text("approve")
                expect(tool_name).to_have_css(
                    "font-family",
                    "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
                )
                expect(page.locator(".execution-section").nth(1)).to_contain_text(
                    "If the caller is the reviewer, derive permission."
                )
                expect(page.locator(".execution-section").nth(2)).to_contain_text(
                    "Allow approval when the actor is the reviewer."
                )
                expect(page.locator(".policy-column .column-caption")).to_have_text(
                    "policy.md"
                )
                expect(page.locator(".review .column-caption")).to_have_text(
                    "Implemented checks"
                )
                expect(
                    page.get_by_text("The actor bound to the current request.")
                ).to_have_count(0)
                expect(page.get_by_text("Input sources", exact=True)).to_have_count(0)
                permission = page.get_by_label(
                    "Capability / access control", exact=True
                )
                information_flow = page.get_by_label("Information flow", exact=True)
                lifecycle = page.get_by_label("State / lifecycle", exact=True)
                definitions = [
                    (
                        permission,
                        "Who is allowed to perform an action.",
                        "Only Professor may approve a job.",
                    ),
                    (
                        information_flow,
                        "What information may be shared with whom.",
                        "Master must not receive PhD’s private information.",
                    ),
                    (
                        lifecycle,
                        "What must already be true or have happened before an action.",
                        "A job must be approved before it can start.",
                    ),
                ]
                for checkbox, definition, example in definitions:
                    tooltip = page.locator(
                        "#" + checkbox.get_attribute("aria-describedby")
                    )
                    expect(tooltip).to_be_hidden()
                    checkbox.locator("..").hover()
                    expect(tooltip).to_be_visible()
                    expect(tooltip).to_contain_text(definition)
                    expect(tooltip).to_contain_text(example)
                    assert not checkbox.is_checked()
                    page.locator("header").hover()
                    expect(tooltip).to_be_hidden()
                permission.focus()
                permission.press("Tab")
                expect(information_flow).to_be_focused()
                tooltip = page.locator(
                    "#" + information_flow.get_attribute("aria-describedby")
                )
                expect(tooltip).to_be_visible()
                page.screenshot(
                    path=str(ROOT / "test-results/student-category-help.png"),
                    full_page=True,
                )
                information_flow.press("Escape")
                expect(tooltip).to_be_hidden()
                expect(information_flow).not_to_be_checked()
                page.get_by_label("Fully matches", exact=True).check()
                page.get_by_label("Capability / access control", exact=True).check()
                page.get_by_role("button", name="Save", exact=True).click()
                expect(page.locator("#save-status")).to_have_text("Saved")
                assert (
                    json.loads(path.read_text())["sentences"][0]["rating"]
                    == "fully_correct"
                )
                page.get_by_label("Policy sentence").select_option("1")
                expect(page.locator(".execution-caption")).to_have_count(0)
                expect(page.locator(".execution-line")).to_have_text(
                    "An older description without stage labels."
                )
                page.get_by_label("Not a policy", exact=True).check()
                page.get_by_role("button", name="Save", exact=True).click()
                expect(
                    page.get_by_label("Capability / access control", exact=True)
                ).to_be_disabled()
                expect(page.locator("#save-status")).to_have_text("Saved")
                assert (
                    json.loads(path.read_text())["sentences"][1]["rating"]
                    == "not_policy"
                )
                expect(page.locator("header a[download]")).to_have_attribute(
                    "download", "review.json"
                )
                exported = page.request.get(
                    f"http://127.0.0.1:{server.server_port}/api/review"
                ).json()
                assert exported == json.loads(path.read_text())
                screenshots = ROOT / "test-results"
                screenshots.mkdir(exist_ok=True)
                page.get_by_label("Policy sentence").select_option("0")
                page.screenshot(
                    path=str(screenshots / "student-review.png"), full_page=True
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
            # A fresh backend with a different empty cache must load the file.
            resumed = StudentStudy(fixture.root / "cache-two", application, path)
            server = Server(("127.0.0.1", 0), resumed)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                page.goto(f"http://127.0.0.1:{server.server_port}")
                expect(page.get_by_label("Fully matches", exact=True)).to_be_checked()
                page.get_by_label("Policy sentence").select_option("1")
                expect(page.get_by_label("Not a policy", exact=True)).to_be_checked()
                screenshots = ROOT / "test-results"
                screenshots.mkdir(exist_ok=True)
                page.screenshot(
                    path=str(screenshots / "student-review-save.png"), full_page=True
                )
                assert not errors, errors
                browser.close()
                print(
                    "Direct review.json Save/Export, non-policy labels, and resume with a fresh cache passed (fixture translation)."
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
    finally:
        fixture.tearDown()


if __name__ == "__main__":
    main()
