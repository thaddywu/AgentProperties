"""Browser checks of both repo job buttons using deterministic backend fixtures."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[2]
for directory in ("src",):
    sys.path.insert(0, str(ROOT / directory))

from policyscope._paths import cache_directory

from playwright.sync_api import sync_playwright, expect
from policyscope.core.policy import fingerprint
from policyscope.workbench.example import Application
from policyscope.policy_adder.repository import PortJobs
from policyscope.workbench.server import Server
from policyscope.workbench.study import Study


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        app = Application()
        study = Study(root / "study", app)

        class FixturePort:
            output = root / "port"

            def translate(self):
                self.output.mkdir(exist_ok=True)
                (self.output / "candidate/policy_port").mkdir(parents=True)
                (self.output / "candidate/policy_port/rules.dl").write_text("fixture")
                (self.output / "translation.json").write_text('{"status":"fixture"}')
                return dict(
                    passed=True, tests=6, artifacts={"trajectories": ["fixture only"]}
                )

            def backtranslate(self):
                return dict(passed=True)

            def review(self):
                review = deepcopy(app.reference())
                review["origin"] = "model"
                review.pop("id")
                review["id"] = fingerprint(review)
                return review

        port = FixturePort()
        port.output.mkdir()
        jobs = PortJobs(port, study)
        server = Server(("127.0.0.1", 0), study, port_jobs=jobs)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}")
                translate = page.get_by_role("button", name="Translate", exact=True)
                back = page.get_by_role("button", name="Back-translate", exact=True)
                expect(translate).to_be_enabled()
                expect(back).to_be_disabled()
                translate.click()
                expect(back).to_be_enabled(timeout=10000)
                expect(translate).to_be_disabled()
                back.click()
                expect(page.get_by_label("Review version")).to_have_value(
                    port.review()["id"], timeout=10000
                )
                expect(
                    page.get_by_role("button", name="Results", exact=True)
                ).to_have_count(0)
                expect(page.get_by_label("Review version")).to_contain_text("Version 2")
                screenshots = cache_directory() / "test-results"
                screenshots.mkdir(exist_ok=True)
                page.screenshot(
                    path=str(screenshots / "codex-buttons.png"), full_page=True
                )
                exported = page.request.get(
                    f"http://127.0.0.1:{server.server_port}/api/export"
                ).json()
                assert len(exported["study"]["reviews"]) == 2
                assert (
                    exported["study"]["applicationEvidence"]["developmentChecks"][
                        "tests"
                    ]
                    == 6
                )
                page.reload()
                expect(
                    page.get_by_role("button", name="Translate", exact=True)
                ).to_be_disabled()
                assert json.loads(jobs.path.read_text())["status"] == "completed"
                assert not errors, errors
                browser.close()
                print(
                    "Repo Translate/Back-translate, saved jobs, review versions, exported evidence and reload passed (fixture model)."
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    main()
