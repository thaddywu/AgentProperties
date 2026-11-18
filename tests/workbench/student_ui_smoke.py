"""Portable review UI: save to review.json and resume with no internal cache."""

import json
from pathlib import Path
import select
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
for directory in ("src",):
    sys.path.insert(0, str(ROOT / directory))

from policyweave._paths import cache_directory

from playwright.sync_api import expect, sync_playwright
from test_student_workflow import StudentWorkflowTests
from policyweave.workbench.student_review import StudentStudy
from policyweave.policy_adder.codex import save
from policyweave.policy_viewer import review_units


def stop_review(process):
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    process.stdout.close()


def start_review(fixture):
    process = subprocess.Popen([
        sys.executable, "-B", "-m", "policyweave", "view-translation",
        "--back-translation", str(fixture.target / "back-translation"),
        "--policy", str(fixture.base / "policy.md"), "--port", "0",
    ], cwd=fixture.root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        if not select.select([process.stdout], [], [], 15)[0]:
            raise AssertionError("view-translation did not start")
        line = process.stdout.readline().strip()
        assert line.startswith("Evaluation UI: http://127.0.0.1:"), line
        return process, line.removeprefix("Evaluation UI: ")
    except BaseException:
        stop_review(process)
        raise


def main():
    fixture = StudentWorkflowTests()
    fixture.setUp()
    try:
        # Keep old verbose titles and unlinked descriptions in the stored bundle;
        # the reviewer should see only relevant business sentences.
        reference_path = fixture.port.output / "review.json"
        reference = json.loads(reference_path.read_text())
        reference["execution"]["procedures"][0]["title"] = "Approval permission"
        reference["execution"]["procedures"][0]["summary"] = "The reviewer can approve requests before the original approval action runs."
        reference["execution"]["procedures"][0]["examples"] = [dict(
            scenario="A student requests approval.",
            outcome="This permission check does not grant the request.", ruleIds=["rule1"],
        )]
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
        reference = application.reference()
        study.judge(
            reference["id"],
            review_units(reference)["units"][0]["id"],
            dict(rating="unsure", categories=["uncertain"], note=""),
        )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            server, review_url = start_review(fixture)
            try:
                page.goto(review_url)
                expect(page.get_by_label("Not sure", exact=True)).to_have_count(0)
                expect(page.locator('[name="rating"]')).to_have_count(4)
                expect(page.locator('[name="categories"]')).to_have_count(4)
                page.get_by_role("button", name="Next", exact=True).click()
                page.get_by_role("button", name="Previous", exact=True).click()
                legacy = json.loads(path.read_text())["sentences"][0]
                assert legacy["rating"] == "unsure"
                assert legacy["categories"] == ["uncertain"]
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
                expect(page.get_by_role("heading", name="Approval permission", exact=True)).to_be_visible()
                expect(
                    page.get_by_text("An unrelated implementation detail.")
                ).to_have_count(0)
                expect(page.locator(".execution-caption")).to_have_count(0)
                expect(page.locator(".execution-lines")).to_be_hidden()
                expect(page.get_by_text("A student requests approval.", exact=True)).to_be_hidden()
                page.get_by_text("How this is checked", exact=True).click()
                expect(page.locator(".execution-line").nth(0)).to_contain_text(
                    "Before approve, the application supplies the caller role."
                )
                tool_name = page.locator(".execution-line code")
                expect(tool_name).to_have_text("approve")
                expect(tool_name).to_have_css(
                    "font-family",
                    "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
                )
                expect(page.locator(".execution-line").nth(1)).to_contain_text(
                    "If the caller is the reviewer, derive permission."
                )
                expect(page.locator(".execution-line").nth(2)).to_contain_text(
                    "Allow approval when the actor is the reviewer."
                )
                page.get_by_text("Examples", exact=True).click()
                expect(page.get_by_text("A student requests approval.", exact=True)).to_be_visible()
                expect(page.get_by_text("This permission check does not grant the request.", exact=True)).to_be_visible()
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
                    path=str(
                        cache_directory() / "test-results/student-category-help.png"
                    ),
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
                assert json.loads(path.read_text())["sentences"][0]["categories"] == ["permission"]
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
                    f"{review_url}/api/review"
                ).json()
                assert exported == json.loads(path.read_text())
                # Exercise the browser download, including an edit whose autosave
                # has not yet run, rather than only reading the JSON endpoint.
                page.get_by_role("button", name="Add a note", exact=True).click()
                page.get_by_label("Comment", exact=True).fill("Synthetic note entered before export.")
                with page.expect_download() as event:
                    page.get_by_role("link", name="Export", exact=True).click()
                download = event.value
                assert download.suggested_filename == "review.json"
                assert download.failure() is None
                exported = json.loads(Path(download.path()).read_text())
                assert exported == json.loads(path.read_text())
                assert exported["sentences"][1]["note"] == "Synthetic note entered before export."
                assert page.url.startswith(review_url)
                screenshots = cache_directory() / "test-results"
                screenshots.mkdir(exist_ok=True)
                page.get_by_label("Policy sentence").select_option("0")
                page.screenshot(
                    path=str(screenshots / "student-review.png"), full_page=True
                )
            finally:
                stop_review(server)
            # A fresh backend with a different empty cache must load the file.
            shutil.rmtree(fixture.target / "back-translation/.review-state")
            server, review_url = start_review(fixture)
            try:
                page.goto(review_url + "/#sentence=2")
                expect(page.get_by_label("Policy sentence")).to_have_value("1")
                expect(page.get_by_label("Not a policy", exact=True)).to_be_checked()
                page.get_by_label("Policy sentence").select_option("0")
                expect(page.get_by_label("Fully matches", exact=True)).to_be_checked()
                page.get_by_label("Policy sentence").select_option("1")
                screenshots = cache_directory() / "test-results"
                screenshots.mkdir(exist_ok=True)
                page.screenshot(
                    path=str(screenshots / "student-review-save.png"), full_page=True
                )
                assert not errors, errors
                browser.close()
                print(
                    "view-translation CLI, review.json Save/Export, and resume with a fresh cache passed (fixture translation)."
                )
            finally:
                stop_review(server)
    finally:
        fixture.tearDown()


if __name__ == "__main__":
    main()
