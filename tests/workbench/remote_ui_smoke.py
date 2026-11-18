"""Actual downloads and slow-model QA through a different loopback port."""

from contextlib import contextmanager
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from playwright.sync_api import expect, sync_playwright
from policyweave._paths import cache_directory
from policyweave.workbench.analysis import AnalysisServer
from policyweave.workbench.example import Application
from policyweave.workbench.server import Server
from policyweave.workbench.study import Study
from tests.analysis.test_call_analysis import CallAnalysisTests


@contextmanager
def serve(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://localhost:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def forwarding(backend):
    class Forward(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def forward(self):
            connection = http.client.HTTPConnection("127.0.0.1", backend.server_port, timeout=1)
            try:
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                # Preserve browser Host and Origin, just like a TCP/SSH tunnel.
                connection.request(self.command, self.path, body, dict(self.headers))
                response = connection.getresponse()
                content = response.read()
                self.send_response(response.status)
                for name, value in response.getheaders():
                    if name.lower() not in {"server", "date", "connection"}:
                        self.send_header(name, value)
                self.end_headers()
                self.wfile.write(content)
            except (OSError, http.client.HTTPException):
                self.send_error(504)
            finally:
                connection.close()

        do_GET = do_POST = forward

    return ThreadingHTTPServer(("127.0.0.1", 0), Forward)


def main():
    screenshots = cache_directory() / "test-results"
    screenshots.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory, sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport=dict(width=1420, height=1040))
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        study = Study(directory, Application())
        backend = Server(("127.0.0.1", 0), study)
        started, release = threading.Event(), threading.Event()
        judge = study.judge

        def delayed_save(*args):
            started.set()
            if not release.wait(5):
                raise TimeoutError()
            return judge(*args)

        with serve(backend), serve(forwarding(backend)) as base:
            page.goto(base)
            page.get_by_label("Fully matches", exact=True).check()
            expect(page.locator("#save-status")).to_have_text("Saved")
            page.get_by_role("button", name="Add a note", exact=True).click()
            with patch.object(study, "judge", side_effect=delayed_save):
                page.get_by_label("Comment", exact=True).fill("Synthetic note saved before download.")
                try:
                    with page.expect_download() as event:
                        page.get_by_role("link", name="Export", exact=True).click()
                        assert started.wait(2)
                        release.set()
                    download = event.value
                    assert download.suggested_filename == "policy-study.json"
                    assert download.failure() is None
                    value = json.loads(Path(download.path()).read_text())
                    histories = value["study"]["judgments"].values()
                    assert any(history[-1]["note"] == "Synthetic note saved before download."
                               for units in histories for history in units.values())
                finally:
                    release.set()
            assert page.url.rstrip("/") == base
            # Failed exports stay on the review and provide an actionable error.
            page.route("**/api/export", lambda route: route.fulfill(
                status=500, content_type="application/json", body='{"error":"Synthetic export failure."}'))
            page.get_by_role("link", name="Export", exact=True).click()
            expect(page.locator("#message")).to_have_text("Synthetic export failure.")
            page.unroute("**/api/export")
            with page.expect_download():
                page.get_by_role("link", name="Export", exact=True).click()
            expect(page.locator("#message")).to_be_empty()
            page.screenshot(path=str(screenshots / "remote-review-export.png"), full_page=True)

        fixture = CallAnalysisTests()
        try:
            timeline, trajectory = fixture.capture()
            generate = fixture.model([])
            started, release = threading.Event(), threading.Event()
            fail = False

            def model(stage, prompt):
                if stage == "call-analysis-answer":
                    started.set()
                    if not release.wait(10):
                        raise TimeoutError()
                    if fail:
                        raise RuntimeError("synthetic-private-model-error")
                return generate(stage, prompt)

            backend = AnalysisServer(("127.0.0.1", 0), trajectory, model)
            with serve(backend), serve(forwarding(backend)) as base:
                page.goto(base)
                page.get_by_role("tab", name="QA", exact=True).click()
                page.get_by_role("button", name="Analysis", exact=True).click()
                assert started.wait(2)
                expect(page.locator("#call-status")).to_have_text("Explaining this call…")
                # Four progress reads span longer than this proxy's request timeout.
                page.wait_for_function("""() => performance.getEntriesByType('resource')
                    .filter(entry => entry.name.includes('/api/analysis/jobs/')).length >= 4""")
                page.screenshot(path=str(screenshots / "remote-analysis-progress.png"), full_page=True)
                release.set()
                expect(page.locator("#call-answer .analysis-answer")).to_have_text("Recorded call evidence.")
                expect(page.get_by_role("button", name="Analysis", exact=True)).to_be_enabled()
                assert page.request.get(base + "/api/analysis/export").json() == trajectory
                fail = True
                page.get_by_role("button", name="Analysis", exact=True).click()
                expect(page.locator("#call-answer")).to_contain_text("Analysis failed")
                expect(page.locator("#call-status")).to_be_empty()
                expect(page.locator("#call-answer")).not_to_contain_text("synthetic-private-model-error")
                expect(page.get_by_role("button", name="Analysis", exact=True)).to_be_enabled()
                fail = False
                page.get_by_role("button", name="Analysis", exact=True).click()
                expect(page.locator("#call-answer .analysis-answer")).to_have_text("Recorded call evidence.")
                page.screenshot(path=str(screenshots / "remote-analysis-answer.png"), full_page=True)
        finally:
            release.set()
            fixture.doCleanups()
        assert not errors, errors
        browser.close()
    print("Forwarded-port downloads, save ordering, slow-model progress and failure/retry passed.")


if __name__ == "__main__":
    main()
