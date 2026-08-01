"""The Markdown to HTML conversion behind the help and `wimba docs`.

Qt renders Markdown but discards tables, and the documentation is largely
tables, so the conversion is what makes the help readable at all.
"""
import re

import pytest

from wimba.docsgen import (ALLOWED_TAGS, SECTIONS, STYLESHEET, WEB_STYLESHEET,
                            build_html_docs, markdown_to_html)


def test_tables_survive():
    """The reason this converter exists."""
    html = markdown_to_html("| A | B |\n|---|---|\n| 1 | 2 |\n")
    assert "<table>" in html
    assert "<th>A</th>" in html and "<th>B</th>" in html
    assert "<td>1</td>" in html and "<td>2</td>" in html


def test_table_rows_are_padded_to_the_header_width():
    html = markdown_to_html("| A | B | C |\n|---|---|---|\n| 1 |\n")
    assert html.count("<td>") == 3


def test_headings_lists_and_rules():
    html = markdown_to_html("# One\n\n## Two\n\n- a\n- b\n\n1. x\n2. y\n\n---\n")
    assert '<h1 id="one">' in html and "One</h1>" in html
    assert '<h2 id="two">' in html and "Two</h2>" in html
    assert "<ul><li>a</li><li>b</li></ul>" in html
    assert "<ol><li>x</li><li>y</li></ol>" in html
    assert "<hr>" in html


def test_code_fences_are_escaped_and_not_interpreted():
    html = markdown_to_html("```\n# not a heading\n<b>literal</b>\n```\n")
    assert "<pre><code>" in html
    assert "&lt;b&gt;literal&lt;/b&gt;" in html
    assert "<h1>" not in html


def test_inline_code_is_not_further_interpreted():
    html = markdown_to_html("use `**not bold**` here")
    assert "<code>**not bold**</code>" in html
    assert "<b>" not in html


def test_emphasis_links_and_images():
    html = markdown_to_html(
        "**b** and *i* and [t](IW2D.md) and ![alt](fig.png)")
    assert "<b>b</b>" in html and "<i>i</i>" in html
    assert '<a href="IW2D.md">t</a>' in html
    assert '<img src="fig.png" alt="alt">' in html


def test_allowed_html_passes_through():
    """Markdown allows inline HTML and the documentation uses it for what
    Markdown cannot express -- a centred logo, an image with a width."""
    src = ('<p align="center">\n'
           '<img src="img/wimba_logo.png" alt="WIMBA" width="400">\n'
           '</p>\n'
           '<p align="center"><em>Wake &amp; Impedance Model Builder</em></p>\n')
    html = markdown_to_html(src)
    assert '<p align="center">' in html
    assert '<img src="img/wimba_logo.png"' in html and 'width="400"' in html
    assert "<em>" in html
    assert "&amp;amp;" not in html and "&amp;" in html   # entity not doubled


def test_allowed_html_inline_in_a_paragraph():
    html = markdown_to_html("text with <b>bold</b> and <br> a break")
    assert "<b>bold</b>" in html and "<br>" in html


def test_html_outside_the_allowlist_is_escaped():
    """Documentation is text, not markup to execute."""
    for bad in ("<script>alert(1)</script>", "<iframe src=x>", "<object>"):
        html = markdown_to_html(f"a {bad} b")
        tag = bad[1:].split(">")[0].split()[0]
        assert f"<{tag}" not in html, bad
        assert "&lt;" in html
    assert "script" not in ALLOWED_TAGS and "iframe" not in ALLOWED_TAGS


def test_blockquote_keeps_its_inner_markup():
    html = markdown_to_html("> **warning**\n> second line\n")
    assert "<blockquote>" in html and "<b>warning</b>" in html


def test_full_document_carries_the_stylesheet():
    html = markdown_to_html("# T\n", body_only=False, title="T")
    assert html.startswith("<!DOCTYPE html>")
    assert "<style>" in html and "table" in html


def test_build_writes_pages_an_index_and_a_stylesheet(tmp_path):
    src = tmp_path / "docs"
    src.mkdir()
    (src / "ONE.md").write_text("# One\n\nSee [two](TWO.md).\n")
    (src / "TWO.md").write_text("# Two\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
    (tmp_path / "README.md").write_text("# Readme\n")

    written = build_html_docs(source=src)
    out = src / "html"
    assert (out / "index.html").is_file()
    assert (out / "style.css").is_file()
    for name in ("ONE.html", "TWO.html", "README.html"):
        assert (out / name).is_file(), name
    assert written[0] == out / "index.html"

    # links between documents point at the generated pages
    assert 'href="TWO.html"' in (out / "ONE.html").read_text()
    # the index lists every page
    index = (out / "index.html").read_text()
    assert 'href="ONE.html"' in index and 'href="TWO.html"' in index
    # tables really are tables
    assert "<table>" in (out / "TWO.html").read_text()


def test_build_copies_referenced_images(tmp_path):
    src = tmp_path / "docs"
    src.mkdir()
    (src / "fig.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (src / "P.md").write_text("# P\n\n![a figure](fig.png)\n")
    build_html_docs(source=src, extra=())
    assert (src / "html" / "fig.png").is_file()


def test_build_copies_images_referenced_by_html_tags(tmp_path):
    """The README points at its logo with <img>, not with Markdown."""
    src = tmp_path / "docs"
    src.mkdir()
    (src / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (src / "P.md").write_text('# P\n\n<p><img src="logo.png" width="80"></p>\n')
    build_html_docs(source=src, extra=())
    assert (src / "html" / "logo.png").is_file()


def test_build_reports_a_missing_source(tmp_path):
    with pytest.raises(FileNotFoundError, match="docs/ directory"):
        build_html_docs(source=tmp_path / "nowhere")


def test_help_browser_renders_tables():
    """End to end: a documentation section containing a table reaches the
    widget as a table."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    from wimba.gui.help_browser import HelpBrowser
    app = QApplication.instance() or QApplication([])   # keep a reference
    assert app is not None
    dlg = HelpBrowser()
    dlg.box.setText("frequency grid")
    assert dlg.hits.count() > 0
    dlg.hits.setCurrentRow(0)
    assert "<table" in dlg.view.toHtml().lower()


def test_image_sources_point_at_the_copies(tmp_path):
    """The output is a flat folder, so a relative path leading out of it would
    break; the copies are referenced instead."""
    root = tmp_path
    (root / "img").mkdir()
    (root / "img" / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    src = root / "docs"
    src.mkdir()
    (src / "P.md").write_text('# P\n\n<img src="../img/logo.png" width="80">\n')

    build_html_docs(source=src, extra=())
    page = (src / "html" / "P.html").read_text()
    assert 'src="logo.png"' in page
    assert "../img" not in page
    assert (src / "html" / "logo.png").is_file()


def test_documents_sharing_a_stem_both_survive(tmp_path):
    """A README at the root and one in docs/ must not overwrite each other."""
    root = tmp_path
    (root / "README.md").write_text("# Root readme\n")
    src = root / "docs"
    src.mkdir()
    (src / "README.md").write_text("# Docs index\n")

    build_html_docs(source=src)
    out = src / "html"
    assert (out / "README.html").is_file()
    assert (out / "docs_README.html").is_file()
    assert "Root readme" in (out / "README.html").read_text()
    assert "Docs index" in (out / "docs_README.html").read_text()


def test_headings_carry_anchors_in_both_forms():
    """id for a browser, <a name> for Qt: scrollToAnchor does not follow ids."""
    html = markdown_to_html("## Installing IW2D\n")
    assert 'id="installing-iw2d"' in html
    assert '<a name="installing-iw2d"></a>' in html


def test_code_blocks_are_highlighted_by_language():
    html = markdown_to_html("```python\nimport os  # note\nx = 12\n```\n")
    assert 'class="lang-python"' in html
    assert '<span class="k">import</span>' in html
    assert '<span class="c"># note</span>' in html
    assert '<span class="n">12</span>' in html


def test_highlighting_does_not_reprocess_its_own_markup():
    """Highlighting in several passes would turn the attribute of a span into a
    keyword inside another span."""
    html = markdown_to_html("```python\n# import is a word here\nx = 12\n```\n")
    assert '<span class="c"># import is a word here</span>' in html
    assert '<span class="n">12</span>' in html
    assert "<span <span" not in html


def test_table_rows_alternate():
    html = markdown_to_html("| A |\n|---|\n| 1 |\n| 2 |\n| 3 |\n")
    assert "<table>" in html                       # a single column is a table
    assert html.count('<tr class="odd">') == 1     # rows 1 and 3 plain, 2 odd


def test_a_horizontal_rule_is_not_a_table_separator():
    html = markdown_to_html("text\n\n---\n\nmore\n")
    assert "<hr>" in html and "<table>" not in html


def _mini_docs(tmp_path):
    root = tmp_path
    (root / "img").mkdir()
    (root / "img" / "wimba_logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (root / "README.md").write_text(
        '<p align="center"><img src="img/wimba_logo.png"></p>\n\n# WIMBA\n\nIntro.\n')
    src = root / "docs"
    src.mkdir()
    (src / "SETUP.md").write_text("# Setup\n\n## One\n\na\n\n## Two\n\nb\n\n## Three\n\nc\n")
    (src / "IW2D.md").write_text("# IW2D\n\nSee [setup](SETUP.md).\n")
    return src


def test_generated_page_has_sidebar_header_and_contents(tmp_path):
    src = _mini_docs(tmp_path)
    build_html_docs(source=src)
    page = (src / "html" / "SETUP.html").read_text()
    assert '<aside class="sidebar">' in page
    assert 'id="title-block-header"' in page
    assert '<div class="toc">' in page and 'href="#one"' in page
    assert 'class="current"' in page
    assert '<link rel="stylesheet" href="style.css">' in page
    assert '<script src="sidebar.js">' in page


def test_sidebar_groups_pages_into_sections(tmp_path):
    src = _mini_docs(tmp_path)
    build_html_docs(source=src)
    page = (src / "html" / "IW2D.html").read_text()
    assert "Getting started" in page and "Engines" in page
    # the section holding the current page is open, others collapsed
    assert 'nav-section collapsed' in page and 'class="nav-section" ' in page


def test_stylesheet_and_script_are_written(tmp_path):
    src = _mini_docs(tmp_path)
    build_html_docs(source=src)
    css = (src / "html" / "style.css").read_text()
    js = (src / "html" / "sidebar.js").read_text()
    assert ".sidebar" in css and "table" in css
    assert "nav-section-header" in js
    assert css.isascii() and js.isascii()


def test_short_documents_get_no_contents_list(tmp_path):
    src = _mini_docs(tmp_path)
    build_html_docs(source=src)
    assert '<div class="toc">' not in (src / "html" / "IW2D.html").read_text()


def test_sections_reference_existing_documents():
    """The sidebar grouping must not drift from the files on disk."""
    from wimba.gui.help_index import find_docs
    stems = {p.stem for p in find_docs()} | {"docs_README"}
    for name, listed in SECTIONS:
        for stem in listed:
            assert stem in stems, f"{name}: {stem}.md is not in the documentation"


def test_no_backslash_inside_an_fstring_expression():
    """The package declares requires-python >= 3.10, and a backslash inside an
    f-string expression is accepted only from 3.12 (PEP 701). It parses fine on
    a newer interpreter and fails at import on an older one, so a check that
    runs on any interpreter is the only useful one.

    The AST cannot answer this: get_source_segment on a FormattedValue returns
    the whole literal, not the expression. A textual check is what works.
    """
    import pathlib

    fstring = re.compile(r"(?<![\w.])[rRbB]?[fF][rR]?['\"]")
    braces_with_backslash = re.compile(r"\{[^{}\n]*\\[^{}\n]*\}")

    root = pathlib.Path(__file__).resolve().parents[1]
    offenders = []
    for f in sorted((root / "wimba").rglob("*.py")):
        for lineno, line in enumerate(f.read_text().splitlines(), 1):
            if fstring.search(line) and braces_with_backslash.search(line):
                offenders.append(f"{f.relative_to(root)}:{lineno}: {line.strip()[:70]}")
    assert not offenders, (
        "backslash inside an f-string expression (needs Python 3.12):\n  "
        + "\n  ".join(offenders))


def test_a_heading_glued_to_an_html_block_is_still_a_heading():
    """Documents put a centred logo immediately above the title, with no blank
    line between. Swallowing the title into the raw block would print it as
    literal text."""
    src = ('<p align="center"><img src="img/logo.png" width="190"></p>\n'
           "# External data files\n\nBody.\n")
    html = markdown_to_html(src)
    assert '<p align="center">' in html
    assert 'id="external-data-files"' in html
    assert "# External data" not in html


def test_multi_line_html_block_still_passes_through():
    src = ('<p align="center">\n'
           '  <img src="img/logo.png" width="190">\n'
           "</p>\n\n# Title\n")
    html = markdown_to_html(src)
    assert '<img src="img/logo.png" width="190">' in html
    assert 'id="title"' in html


def test_every_shipped_document_renders_its_title_as_a_heading():
    """A regression guard over the real documentation, both logo styles."""
    from wimba.gui.help_index import find_docs
    for path in find_docs():
        text = path.read_text(errors="replace")
        first = next((l[2:].strip() for l in text.splitlines()
                      if l.startswith("# ")), None)
        if first is None:
            continue
        html = markdown_to_html(text)
        assert "<h1" in html, f"{path.name}: no h1 rendered"
        assert f"\n# {first}" not in html, f"{path.name}: title left as text"
