"""Render the student Markdown instructions, including review screenshots, to PDF.

Optional document dependencies: markdown-it-py, Playwright and Chromium.
Fonts are cached outside the checkout; no font binaries are committed.
"""

import argparse
import hashlib
import html
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
FONT_URL = "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/SimplifiedChinese/"


def markdown(source):
    from markdown_it import MarkdownIt

    return MarkdownIt("commonmark", {"html": False}).enable("table").render(source)


def document(source, fonts, source_directory):
    content = markdown(source)
    # Chromium resolves relative document links against the local file base.
    # Keep their text without exporting machine-specific file URI annotations.
    content = re.sub(
        r'<a href="([^"]+)"[^>]*>(.*?)</a>',
        lambda match: (
            match[0]
            if match[1].startswith(("https://", "http://", "mailto:"))
            else "<span>" + match[2] + "</span>"
        ),
        content,
        flags=re.S,
    )
    for appendix in ("A", "C"):
        content = content.replace(
            "<h2>Appendix " + appendix + ".",
            '<h2 class="new-page">Appendix ' + appendix + ".",
        )
    # Keep each screenshot with its example heading and explanation.
    examples = content.find("<h3>")
    if examples >= 0:
        content = content[:examples] + "".join(
            '<section class="example"><h3>' + part + "</section>"
            for part in content[examples:].split("<h3>")[1:]
        )
    font_css = "".join(
        '@font-face {font-family:InstructionCN;src:url("'
        + font.as_uri()
        + '");font-weight:'
        + weight
        + "}"
        for font, weight in zip(fonts, ("400", "700"))
    )
    language = "zh-CN" if fonts else "en"
    return (
        '<!doctype html><html lang="'
        + language
        + '"><head><meta charset="utf-8">'
        + '<base href="'
        + html.escape(source_directory.as_uri() + "/", quote=True)
        + '">'
        + "<title>Phase 2: Translate, Review, Test</title><style>"
        + font_css
        + """
@page {size:A4;margin:16mm 17mm 18mm}
* {box-sizing:border-box}
body {margin:0;color:#20242b;font-family:InstructionCN,"DejaVu Sans",sans-serif;font-size:10.1pt;line-height:1.48}
h1 {font-size:20pt;line-height:1.25;margin:0 0 13pt;font-weight:700;letter-spacing:-.3pt}
h2 {font-size:13pt;line-height:1.35;margin:16pt 0 8pt;font-weight:700;break-after:avoid}
h3 {font-size:11.3pt;line-height:1.4;margin:13pt 0 8pt;break-after:avoid}
h2.new-page,.example + .example {break-before:page;margin-top:0}
.example {break-inside:avoid}
p {margin:0 0 8pt;orphans:3;widows:3}
p:has(+ ul),p:has(+ ol),p:has(+ pre),p:has(+ table) {break-after:avoid}
ul,ol {margin:6pt 0 10pt;padding-left:18pt}
li {margin:3pt 0;break-inside:avoid}
li p {margin:0}
code {font-family:"DejaVu Sans Mono",InstructionCN,monospace;font-size:8.5pt;overflow-wrap:anywhere}
p code,li code {background:#f1f3f5;padding:0 2pt;border-radius:2pt}
pre {margin:8pt 0 10pt;padding:9pt 11pt;background:#f4f5f7;border-left:2pt solid #c7cdd4;
     white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.4;break-inside:avoid}
pre code {font-size:8pt;line-height:1.4}
table {width:100%;border-collapse:collapse;margin:8pt 0 10pt;font-size:8.7pt;table-layout:fixed}
th,td {border:1px solid #d5d9dd;padding:5pt 7pt;text-align:left;vertical-align:top;overflow-wrap:anywhere}
th:first-child,td:first-child {width:24%}
tr {break-inside:avoid}
img {display:block;max-width:100%;height:auto;max-height:204mm;object-fit:contain;margin:10pt auto 0}
a {color:#245272;text-decoration:none}
</style></head><body>"""
        + content
        + "</body></html>"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source", type=Path, default=ROOT / "docs/study/student-workflow.md"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "output/docs/student-workflow.pdf"
    )
    parser.add_argument(
        "--font-dir",
        type=Path,
        default=Path.home() / ".cache/policyscope/document-fonts",
    )
    args = parser.parse_args()
    source = args.source.read_text()
    fonts = []
    if re.search(r"[\u3400-\u9fff]", source):
        args.font_dir.mkdir(parents=True, exist_ok=True)
        for weight in ("Regular", "Bold"):
            name = "NotoSansCJKsc-" + weight + ".otf"
            path = args.font_dir / name
            if not path.exists():
                with urlopen(FONT_URL + name, timeout=60) as response:
                    path.write_bytes(response.read())
            fonts.append(path.resolve())
    from playwright.sync_api import sync_playwright

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        # file:// permits local font embedding without any rendering-time network.
        with TemporaryDirectory(prefix="student-instructions-") as directory:
            rendered = Path(directory) / "instructions.html"
            rendered.write_text(document(source, fonts, args.source.resolve().parent))
            page.goto(rendered.as_uri())
            page.evaluate("document.fonts.ready")
            missing = page.locator("img").evaluate_all(
                '(images) => images.filter(i => !i.complete || !i.naturalWidth).map(i => i.getAttribute("src"))'
            )
            if missing:
                raise ValueError("Missing screenshot images: " + ", ".join(missing))
            page.pdf(
                path=str(args.output),
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
                display_header_footer=True,
                header_template="<span></span>",
                footer_template='<div style="font-size:9px;color:#777;width:100%;padding:0 17mm;display:flex;justify-content:space-between"><span>Phase 2</span><span class="pageNumber"></span></div>',
            )
        browser.close()
    print(str(args.output))
    print("Source SHA-256: " + hashlib.sha256(source.encode()).hexdigest())


if __name__ == "__main__":
    main()
