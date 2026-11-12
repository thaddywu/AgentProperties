"""Integration/browser journey against an actual accepted port; no model calls.

Run after port.py: python evaluation/tests/port_smoke.py --ported-app OUTPUT
Requires Docker, the pinned image and the ordinary browser test dependencies.
"""

import argparse
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for directory in ("runtime/python", "translation/python", "query/python", "evaluation"):
    sys.path.insert(0, str(ROOT / directory))

from playwright.sync_api import expect, sync_playwright
from policy_evaluation.cases import run_cases
from policy_evaluation.porting.application import PortedApplication
from policy_evaluation.server import Server
from policy_evaluation.study import Study


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ported-app", required=True, type=Path)
    args = parser.parse_args()
    app = PortedApplication(args.ported_app)
    screenshots = ROOT / "evaluation/test-results"
    screenshots.mkdir(exist_ok=True, parents=True)
    with tempfile.TemporaryDirectory() as directory:
        study = Study(directory, app)
        server = Server(("127.0.0.1", 0), study)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page(viewport=dict(width=1380, height=920))
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}")
                expect(page.locator("header")).not_to_contain_text("LabCluster")
                expect(page.get_by_label("Policy sentence")).to_be_visible()
                page.get_by_role("button", name="Next", exact=True).click()
                expect(page.get_by_label("Policy sentence")).to_have_value("1")
                page.get_by_label("Policy sentence").select_option("3")
                expect(page.get_by_text("Datalog", exact=True)).to_have_count(0)
                expect(
                    page.get_by_text("Conditions & sources", exact=True)
                ).to_have_count(0)
                if app.reference().get("execution"):
                    page.get_by_label("Policy sentence").select_option("6")
                    expect(page.locator(".execution-card").first).to_contain_text(
                        "Master"
                    )
                    expect(page.locator(".behaviors")).not_to_contain_text(
                        "View the cluster"
                    )
                page.get_by_label("Fully matches", exact=True).check()
                page.get_by_label("Capability / access control", exact=True).check()
                expect(page.locator("#save-status")).to_have_text("Saved")
                page.screenshot(
                    path=str(screenshots / "ported-translation.png"), full_page=True
                )
                # Paired execution stays available through the backend and CLI.
                run_cases(study, dict(version=1, cases=[dict(
                    id="quota", task="Submit above the core quota.",
                    setup=dict(scenario="quota_cores"),
                    expected="Block admission without creating the job.",
                )]))
                pair = study.export()["pairs"][0]
                assert pair["comparable"] and pair["policyOrigin"] == "agent-generated"
                before = pair["runs"]["baseline"]["events"][0]
                after = pair["runs"]["protected"]["events"][0]
                assert before["effectCalled"] and len(before["after"]["jobs"]) == 1
                assert not after["effectCalled"] and not after["after"]["jobs"]
                assert not errors, errors
                browser.close()
            print(
                "Actual generated port: independent review, paired execution, callback evidence, human judgment and browser journey passed."
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    main()
