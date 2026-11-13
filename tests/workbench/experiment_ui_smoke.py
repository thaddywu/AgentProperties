"""Paired-execution UI contract with an explicit fixture runner, no hosted model."""

import json
from pathlib import Path
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from playwright.sync_api import sync_playwright, expect
from policyscope._paths import cache_directory
from policyscope.core.artifacts import save
from policyscope.workbench.analysis import AnalysisServer
from policyscope.workbench.experiment import Experiment, ExperimentServer


def main():
    example = json.loads((ROOT / "examples/trajectories/team-review.json").read_text())
    case = dict(
        id="synthetic-paired-case",
        task="Run the explicit offline UI fixture in both modes.",
        expected="Both fixture traces remain available for inspection.",
    )
    with tempfile.TemporaryDirectory() as directory:
        viewer = AnalysisServer(("127.0.0.1", 0), example)

        def execute(case, repetitions, destination):
            rows = []
            for mode in ("baseline", "protected"):
                save(destination / (mode + ".json"), example)
                rows.append(
                    dict(
                        caseId=case["id"],
                        mode=mode,
                        repetition=1,
                        taskCompleted=True,
                        violations=[],
                        timeline=mode + ".json",
                    )
                )
            return rows

        experiment = Experiment([case], execute, directory, viewer)
        server = ExperimentServer(("127.0.0.1", 0), experiment)
        threads = [
            threading.Thread(target=s.serve_forever, daemon=True)
            for s in (server, viewer)
        ]
        for thread in threads:
            thread.start()
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page(viewport=dict(width=1380, height=960))
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(f"http://127.0.0.1:{server.server_port}")
                page.get_by_label("Repetitions", exact=True).select_option("1")
                page.get_by_role("button", name="Run pair", exact=True).click()
                expect(page.locator("#job-status")).to_contain_text("completed")
                expect(page.locator("table tr")).to_have_count(3)
                expect(page.locator("table")).to_contain_text("Original")
                expect(page.locator("table")).to_contain_text("Translated")
                with page.expect_popup() as popup:
                    page.get_by_role(
                        "button", name="Inspect translated", exact=True
                    ).click()
                analysis = popup.value
                analysis.wait_for_load_state("networkidle")
                expect(analysis.locator(".event")).to_have_count(6)
                screenshots = cache_directory() / "test-results"
                screenshots.mkdir(parents=True, exist_ok=True)
                page.screenshot(
                    path=str(screenshots / "paired-study.png"), full_page=True
                )
                assert not errors, errors
                browser.close()
        finally:
            for service in (server, viewer):
                service.shutdown()
                service.server_close()
            for thread in threads:
                thread.join()
    print(
        "Registered fixture runner, paired results and separate read-only inspection passed."
    )


if __name__ == "__main__":
    main()
