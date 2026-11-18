"""Capture the course Inspector figures from a running server and recorded calls."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--event", required=True, help="Recorded blocked agent tool call")
    parser.add_argument("--all-questions", action="store_true", help="Verify and capture every preset")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport=dict(width=1440, height=1100),
                                device_scale_factor=2, color_scheme="light")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        metadata = page.request.get(args.url + "/api/analysis").json()
        trajectory = metadata["trajectory"]
        agents = [r for r in trajectory["roles"] if r.get("kind", "agent") == "agent"]
        event = next(e for e in trajectory["events"] if e["id"] == args.event)
        assert event["actor"] in {r["id"] for r in agents}
        assert event["kind"] == "tool_call" and event["outcome"] == "blocked"
        message = next(e for e in trajectory["events"]
                       if e["kind"] == "message" and e.get("primary", True)
                       and e.get("recipients") and e["actor"] in {r["id"] for r in agents})
        page.goto(args.url, wait_until="networkidle")
        page.evaluate("document.fonts.ready")
        expect(page.get_by_role("button", name="Filter agent All agents", exact=True)).to_be_visible()
        expect(page.locator("#roles .role")).to_have_count(len(agents) + 1)
        page.locator(f'[data-event-id="{args.event}"]').click()
        expect(page.locator("#detail .call-outcome .badge")).to_have_text("Blocked")
        expect(page.locator("#detail")).to_contain_text(event["tool"])
        expect(page.locator("#status")).to_be_empty()
        # Keep the sender and recipient visible alongside the selected call's database.
        page.get_by_role("tab", name="Evidence", exact=True).click()
        expect(page.locator('#facts [data-predicate="Request"]')).to_contain_text(event["actor"])
        expect(page.locator('#facts [data-predicate="Deny"]')).not_to_contain_text("Not recorded")
        page.locator("#facts details").evaluate_all("nodes => nodes.forEach(n => n.open = ['Request', 'Parameter', 'Deny'].includes(n.dataset.predicate))")
        message_card = page.locator(f'[data-event-id="{message["id"]}"]')
        message_card.scroll_into_view_if_needed()
        # Red outlines are figure annotations; they do not change the app's source.
        outlines = page.locator("#roles .role:not(:first-child)")
        outlines.evaluate_all("nodes => nodes.forEach(n => n.style.outline = '2px solid #dc2626')")
        message_card.evaluate("n => n.style.outline = '2px solid #dc2626'")
        page.screenshot(path=str(args.output / "inspector-overview.png"))
        outlines.evaluate_all("nodes => nodes.forEach(n => n.style.removeProperty('outline'))")
        message_card.evaluate("n => n.style.removeProperty('outline')")
        page.locator(f'[data-event-id="{args.event}"]').click()
        page.locator(f'[data-event-id="{args.event}"]').scroll_into_view_if_needed()
        page.get_by_role("tab", name="Details", exact=True).click()
        expect(page.locator("#detail summary")).to_have_text("Result")
        page.locator("#detail summary").click()
        expect(page.locator("#detail .detail-section")).to_have_attribute("open", "")
        page.screenshot(path=str(args.output / "inspector-details.png"))
        page.get_by_role("tab", name="QA", exact=True).click()
        expect(page.locator('#analysis-tools textarea, #analysis-tools input')).to_have_count(0)
        expect(page.locator('#call-suggestions button')).to_have_count(4)
        presets = ["conditions", "flow", "effect", "decision"] if args.all_questions else ["decision"]
        for preset in presets:
            page.set_viewport_size(dict(width=1440, height=1100))
            page.locator(f'#call-suggestions [data-template-id="{preset}"]').click()
            with page.expect_response(lambda r: r.url.endswith('/api/analysis/explain'), timeout=240000) as response:
                page.get_by_role("button", name="Analysis", exact=True).click()
            result = response.value.json()["result"]
            assert result["status"] == "answered" and result["replayMatches"]
            assert result["supportingQueries"]
            assert any(q["rows"] for q in result["supportingQueries"])
            (args.output / f"inspector-qa-{preset}.json").write_text(json.dumps(result, indent=2))
            expect(page.locator("#call-answer .analysis-answer")).to_be_visible()
            expect(page.get_by_role("region", name="Query result", exact=True).first).to_contain_text(event["actor"])
            page.get_by_text("Translation and query", exact=True).click()
            expect(page.locator("#call-answer")).to_contain_text("Decision replay matched.")
            if preset == "decision":
                expect(page.locator("#call-answer pre").first).to_contain_text("Deny")
            # Capture the complete answer, rows and queries without an inner cutoff.
            height = page.locator(".inspector-body").evaluate("n => n.scrollHeight") + 180
            page.set_viewport_size(dict(width=1440, height=max(1100, height)))
            page.locator(".inspector-body").evaluate("n => n.scrollTop = 0")
            filename = "inspector-qa.png" if preset == "decision" else f"inspector-qa-{preset}.png"
            page.screenshot(path=str(args.output / filename))
        assert not errors, errors
        browser.close()
    print("Captured agents, directed message, blocked call, database and replayed QA query.")


if __name__ == "__main__":
    main()
