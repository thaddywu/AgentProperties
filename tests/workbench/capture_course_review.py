"""Capture real LabCluster review output, plus explicitly annotated excerpts."""

import argparse
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5198")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(
            viewport=dict(width=1360, height=1040), device_scale_factor=2,
            color_scheme="light", bypass_csp=True,
        )
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        workspace = page.request.get(args.url + "/api/study").json()
        reference = workspace["study"]["reviews"][-1]
        rows = workspace["study"]["reviewUnits"][reference["id"]]["units"]
        examples = [
            ("capability", "Only Professor may approve", "Capability / access control"),
            ("ifc", "Neither student may receive", "Information flow (IFC)"),
            ("state", "Before dispatch, require a successful Professor", "State / lifecycle / ordering"),
        ]
        excerpts = []
        for slug, prefix, category in examples:
            index, row = next((i, row) for i, row in enumerate(rows) if row["quote"].startswith(prefix))
            excerpts.append(dict(text=row["quote"], category=category, slug=slug))
            page.goto("about:blank")
            page.goto(args.url + f"/#sentence={index + 1}")
            expect(page.get_by_label("Policy sentence")).to_have_value(str(index))
            expect(page.locator(".execution-card")).to_have_count(len(row["procedureIds"]))
            for detail in page.locator(".execution-details").all():
                detail.locator("summary").click()
            expect(page.locator(".execution-details:not([open])")).to_have_count(0)
            if slug == "state":
                changed = (
                    not page.get_by_label("Fully matches", exact=True).is_checked()
                    or not page.get_by_label("State / lifecycle", exact=True).is_checked()
                )
                page.get_by_label("Fully matches", exact=True).check()
                page.get_by_label("State / lifecycle", exact=True).check()
                page.get_by_role("button", name="Save", exact=True).click()
                if changed:
                    expect(page.locator("#save-status")).to_have_text("Saved")
            page.screenshot(
                path=str(args.output / f"translator-review-{slug}.png"), full_page=True,
            )
        # Teaching annotations use exact excerpts; the real UI and frozen model
        # descriptions are also captured separately above without alterations.
        page.evaluate("""(excerpts) => {
            const source = document.querySelector('.source');
            const originals = [...source.querySelectorAll('button')];
            const selected = originals.find(button => button.getAttribute('aria-pressed') === 'true').textContent;
            const fragment = document.createDocumentFragment();
            for (const excerpt of excerpts) {
                const section = document.createElement('div');
                section.className = 'teaching-excerpt';
                const button = originals.find(button => button.textContent === excerpt.text).cloneNode(true);
                button.setAttribute('aria-pressed', String(excerpt.text === selected));
                section.append(button);
                fragment.append(section);
            }
            source.replaceChildren(fragment);
        }""", excerpts)
        page.add_style_tag(content="""
            .policy-column .source { max-height: none; white-space: normal; }
            .teaching-excerpt + .teaching-excerpt { margin-top: 1.2rem; }
            .teaching-excerpt button { line-height: 1.75; white-space: normal; }
            .figure-annotation { position: absolute; left: 18px; width: 188px;
                color: #31527a; font-size: 13px; line-height: 1.4; font-style: italic; }
            .figure-annotation-heading { font-size: 11px; color: #6c6c68; }
        """)
        page.set_viewport_size(dict(width=1760, height=850))
        expect(page.locator('.source button[aria-pressed="true"]')).to_have_count(1)
        expect(page.get_by_label("Fully matches", exact=True)).to_be_checked()
        expect(page.locator('[name="categories"]:checked')).to_have_count(1)
        page.evaluate("""(excerpts) => {
            const source = document.querySelector('.source');
            const heading = document.createElement('span');
            heading.className = 'figure-annotation figure-annotation-heading';
            heading.textContent = 'Figure annotations · selected excerpts';
            heading.style.top = (source.getBoundingClientRect().top + scrollY - 32) + 'px';
            document.body.append(heading);
            const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            svg.style.cssText = 'position:absolute;inset:0;pointer-events:none;width:100%;height:100%';
            svg.innerHTML = '<defs><marker id="annotation-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6" fill="#31527a"/></marker></defs>';
            for (const [index, excerpt] of excerpts.entries()) {
                const rect = source.querySelectorAll('button')[index].getBoundingClientRect();
                const center = rect.top + scrollY + rect.height / 2;
                const label = document.createElement('span');
                label.className = 'figure-annotation';
                label.textContent = excerpt.category;
                document.body.append(label);
                label.style.top = (center - label.offsetHeight / 2) + 'px';
                const line = document.createElementNS(svg.namespaceURI, 'line');
                for (const [key, value] of Object.entries({x1:212, y1:center, x2:rect.left - 10, y2:center, stroke:'#31527a', 'stroke-width':1, 'marker-end':'url(#annotation-arrow)'})) line.setAttribute(key, value);
                svg.append(line);
            }
            document.body.append(svg);
        }""", excerpts)
        page.screenshot(path=str(args.output / "translator-review-panel-proposed.png"), full_page=True)
        assert not errors, errors
        browser.close()
    print("Captured three expanded real review screens and one annotated teaching overview.")


if __name__ == "__main__":
    main()
