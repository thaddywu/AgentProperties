"""Capture the two course judgments using a generated LabCluster reading."""

import argparse
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Isolated local screenshot review")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    scenarios = [
        ("full", "Master may request CPU only", "Fully matches", "fully_correct",
         "Capability / access control", "permission", ""),
        ("partial", "Neither student may receive", "Partly matches", "partially_correct",
         "Information flow", "information_flow",
         "Job reads check ownership, but message bodies and model contexts can still disclose another student's private information."),
    ]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport=dict(width=1440, height=1100),
                                device_scale_factor=2, color_scheme="light")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        workspace = page.request.get(args.url + "/api/study").json()
        reference = workspace["study"]["reviews"][-1]
        rows = workspace["study"]["reviewUnits"][reference["id"]]["units"]
        for slug, prefix, rating_label, rating, category_label, category, note in scenarios:
            index, row = next((i, row) for i, row in enumerate(rows) if row["quote"].startswith(prefix))
            before = page.request.get(args.url + "/api/review").json()["sentences"][index]
            changed = before["rating"] != rating or before["categories"] != [category] or before["note"] != note
            page.goto("about:blank")
            page.goto(args.url + f"/#sentence={index + 1}")
            expect(page.get_by_label("Policy sentence")).to_have_value(str(index))
            expect(page.locator(".execution-card")).to_have_count(len(row["procedureIds"]))
            procedures = [p for p in reference["execution"]["procedures"] if p["id"] in row["procedureIds"]]
            for card, procedure in zip(page.locator(".execution-card").all(), procedures):
                assert card.locator("h2").inner_text() == procedure["title"]
                assert card.locator(".execution-summary").inner_text() == procedure["summary"]
                assert card.locator(".execution-line").all_text_contents() == [step["text"] for step in procedure["steps"]]
            page.get_by_label(rating_label, exact=True).check()
            page.get_by_label(category_label, exact=True).check()
            if note:
                field = page.get_by_label("What is missing or different?", exact=True)
                if field.input_value() != note:
                    field.fill(note)
            page.get_by_role("button", name="Save", exact=True).click()
            if changed:
                expect(page.locator("#save-status")).to_have_text("Saved")
            for detail in page.locator(".execution-details").all():
                detail.locator("summary").click()
            expect(page.locator(".execution-details:not([open])")).to_have_count(0)
            expect(page.locator('.source button[aria-pressed="true"]')).to_have_count(1)
            submitted = page.request.get(args.url + "/api/review").json()["sentences"][index]
            assert submitted["rating"] == rating
            assert submitted["categories"] == [category]
            assert submitted["note"] == note
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(path=str(args.output / f"phase2-review-{slug}-expanded.png"), full_page=True)
            if slug == "partial":
                for card in page.locator(".execution-card").all():
                    heading = card.locator("h2").inner_text().lower()
                    if not any(word in heading for word in ("private", "ownership")):
                        card.locator(".execution-details summary").click()
            page.set_viewport_size(dict(width=1180, height=1050))
            page.locator('.source button[aria-pressed="true"]').evaluate("node => node.scrollIntoView({block:'center'})")
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(path=str(args.output / f"phase2-review-{slug}-proposed.png"), full_page=True)
        assert not errors, errors
        browser.close()
    print("Captured full capability and partial information-flow examples with saved judgments.")


if __name__ == "__main__":
    main()
