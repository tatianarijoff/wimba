"""The in-application help: indexing the documentation and ranking answers.

The index and the ranking are tested without a display; only the dialog itself
needs Qt.
"""
import pytest

from wimba.gui.help_index import (ALIASES, build_index, expand_query, score,
                                  search, snippet, split_sections)

SAMPLE = """# Title

Preamble text.

## Installing IW2D

Install it into the same virtual environment.

```bash
# this heading inside a fence is not a heading
pip install cppyy
```

## Something else

Nothing to see.
"""


def test_split_sections_ignores_headings_inside_code_fences():
    secs = split_sections(SAMPLE, "X.md")
    titles = [s.title for s in secs]
    assert titles == ["Title", "Installing IW2D", "Something else"]
    assert "pip install cppyy" in secs[1].body


def test_expand_query_drops_stopwords_and_adds_the_documents_words():
    terms = expand_query("how do I open an excel file")
    assert "excel" in terms
    assert "spreadsheet" in terms and "xlsx" in terms   # what the docs say
    assert "how" not in terms and "an" not in terms     # stopwords


def test_score_weights_headings_above_body():
    from wimba.gui.help_index import Section
    in_title = Section("d.md", "Installing IW2D", 2, "nothing relevant here")
    in_body = Section("d.md", "Something else", 2, "installing iw2d is described")
    terms = ["installing", "iw2d"]
    assert score(in_title, terms) > score(in_body, terms)


def test_score_prefers_a_section_matching_several_distinct_terms():
    from wimba.gui.help_index import Section
    both = Section("d.md", "", 0, "the frequency grid is rebuilt")
    one = Section("d.md", "", 0, "frequency frequency frequency frequency")
    terms = ["frequency", "grid"]
    assert score(both, terms) > score(one, terms)


def test_search_returns_nothing_for_an_empty_query():
    assert search([], "") == []
    assert search(build_index(), "   ") == []


def test_snippet_shows_context_around_the_match():
    from wimba.gui.help_index import Section
    s = Section("d.md", "T", 2, "padding " * 40 + "the needle is here " + "tail " * 40)
    out = snippet(s, ["needle"])
    assert "needle" in out and len(out) < 200


def test_index_covers_the_shipped_documentation():
    """The help is only useful if it actually finds the documents."""
    index = build_index()
    assert index, "no documentation indexed"
    docs = {s.doc for s in index}
    for expected in ("README.md", "IW2D.md", "PRECALCULATED.md"):
        assert expected in docs, f"{expected} missing from the help index"


@pytest.mark.parametrize("question, expected_doc", [
    ("excel", "PRECALCULATED.md"),
    ("how do I install IW2D", "IW2D.md"),
    ("the twiss file is missing", "DATA.md"),
    ("why is the frequency grid different", "PYTLWALL_CFG.md"),
])
def test_questions_reach_the_right_document(question, expected_doc):
    hits = search(build_index(), question, limit=3)
    assert hits, f"no answer for {question!r}"
    assert expected_doc in {h.doc for h in hits}, \
        f"{question!r} -> {[h.doc for h in hits]}"


def test_aliases_are_lowercase_and_non_empty():
    for key, values in ALIASES.items():
        assert key == key.lower() and values
        assert all(v == v.lower() for v in values)


def test_help_browser_opens_and_searches():
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    from wimba.gui.help_browser import HelpBrowser
    app = QApplication.instance() or QApplication([])
    dlg = HelpBrowser()
    assert dlg.index
    dlg.box.setText("excel")
    assert dlg.hits.count() > 0
    dlg.box.setText("")                       # back to the contents page
    assert dlg.hits.count() > 0
    dlg.box.setText("zzzzz no such thing")
    assert dlg.hits.count() == 0


def test_help_shows_the_whole_document_not_just_the_section():
    """A section on its own reads poorly -- a preamble is just a logo, a short
    heading one sentence. The search picks the place; the page is what is
    shown."""
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    from wimba.gui.help_browser import HelpBrowser
    app = QApplication.instance() or QApplication([])
    assert app is not None
    dlg = HelpBrowser()
    dlg.box.setText("frequency grid")
    assert dlg.hits.count() > 0
    dlg.hits.setCurrentRow(0)

    section = dlg._current_section()
    shown = dlg.view.toPlainText()
    whole = section.path.read_text(errors="replace")
    # much more than the matched section alone
    assert len(shown) > 3 * len(section.body)
    # the document's own title is present, above the matched section
    first_heading = next(l[2:].strip() for l in whole.splitlines()
                         if l.startswith("# "))
    assert first_heading in shown


def test_section_anchor_matches_the_rendered_heading():
    from wimba.docsgen import markdown_to_html
    from wimba.gui.help_index import split_sections
    secs = split_sections("# T\n\n## Installing IW2D\n\nbody\n", "X.md")
    target = [s for s in secs if s.title == "Installing IW2D"][0]
    assert target.anchor == "installing-iw2d"
    assert f'<a name="{target.anchor}"></a>' in markdown_to_html(
        "## Installing IW2D\n")
