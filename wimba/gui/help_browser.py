"""The Help browser: a search box, a list of matching sections, and the text.

Kept separate from :mod:`wimba.gui.help_index` so the index and the ranking can
be exercised without a display.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QPushButton,
                             QSplitter, QTextBrowser, QVBoxLayout, QWidget)

from ..docsgen import STYLESHEET, markdown_to_html
from .help_index import build_index, expand_query, search, snippet


class HelpBrowser(QDialog):
    """Search the documentation without leaving the application."""

    def __init__(self, parent=None, query: str = ""):
        super().__init__(parent)
        self.setWindowTitle("WIMBA Help")
        self.resize(1000, 640)
        self.index = build_index()
        self._pages = {}          # path -> rendered HTML, converted once

        outer = QVBoxLayout(self)

        top = QHBoxLayout()
        self.box = QLineEdit()
        self.box.setPlaceholderText(
            "Ask a question or type a keyword \u2014 e.g. \u201cexcel\u201d, "
            "\u201chow do I install IW2D\u201d, \u201cPEC boundary\u201d")
        self.box.setClearButtonEnabled(True)
        self.box.textChanged.connect(self._on_query)
        top.addWidget(self.box, 1)
        self.count = QLabel("")
        top.addWidget(self.count)
        outer.addLayout(top)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.hits = QListWidget()
        self.hits.currentItemChanged.connect(self._show_current)
        split.addWidget(self.hits)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        # Qt reads Markdown but drops tables, and the documentation is largely
        # tables: render it to HTML instead.
        self.view.document().setDefaultStyleSheet(STYLESHEET)
        # documents refer to images relatively (img/wimba_logo.png): let the
        # widget resolve them against the directories the documents live in
        roots = []
        for s_ in self.index:
            if s_.path is not None:
                for d in (s_.path.parent, s_.path.parent.parent):
                    if d not in roots:
                        roots.append(d)
        self.view.setSearchPaths([str(d) for d in roots])
        rl.addWidget(self.view)
        row = QHBoxLayout()
        self.where = QLabel("")
        self.where.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(self.where, 1)
        self.open_btn = QPushButton("Open in web browser")
        self.open_btn.setToolTip(
            "Generate the HTML documentation if needed and open this page "
            "outside the application")
        self.open_btn.clicked.connect(self._open_in_browser)
        row.addWidget(self.open_btn)
        rl.addLayout(row)
        split.addWidget(right)
        split.setSizes([320, 680])
        outer.addWidget(split, 1)

        QShortcut(QKeySequence("Ctrl+F"), self,
                  activated=lambda: (self.box.setFocus(), self.box.selectAll()))
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.close)

        if not self.index:
            self.view.setPlainText(
                "The documentation was not found next to the installed package.\n\n"
                "WIMBA reads it from the docs/ directory of the project; it is "
                "there in a checkout (pip install -e), which is how WIMBA is "
                "normally used.\n\n"
                "The same pages are in the repository under docs/.")
            self.box.setEnabled(False)
            return

        self._show_contents()
        if query:
            self.box.setText(query)

    def _render(self, markdown: str):
        """Show Markdown, converted to HTML so tables survive."""
        self.view.setHtml(markdown_to_html(markdown))
        self.view.verticalScrollBar().setValue(0)

    def _show_document(self, section):
        """Show the whole document, scrolled to the section that matched.

        A section on its own reads poorly -- a preamble is just a logo, a short
        heading is one sentence -- and loses the surrounding context that makes
        the page worth reading. The search picks the place; the page is what is
        shown.
        """
        path = section.path
        if path is None:
            self._render(section.body)
            return
        key = str(path)
        if key not in self._pages:
            try:
                self._pages[key] = markdown_to_html(path.read_text(errors="replace"))
            except OSError as exc:
                self._render(f"# Cannot read {path.name}\n\n{exc}")
                return
        self.view.setHtml(self._pages[key])
        if section.anchor:
            self.view.scrollToAnchor(section.anchor)
        else:
            self.view.verticalScrollBar().setValue(0)

    # ---- contents ----------------------------------------------------------

    def _show_contents(self):
        """With an empty box, offer the documents rather than a blank page."""
        self.hits.clear()
        self.count.setText(f"{len(self.index)} sections")
        seen = []
        for s in self.index:
            if s.doc not in seen:
                seen.append(s.doc)
        lines = ["# WIMBA documentation", "",
                 "Type a question or a keyword above. The search also follows "
                 "the words the documents actually use, so \u201cexcel\u201d "
                 "finds the pages about spreadsheets.", "", "## Pages", ""]
        for doc in seen:
            first = next(s for s in self.index if s.doc == doc)
            title = first.title or doc[:-3]
            lines.append(f"- **{doc[:-3]}** \u2014 {title}")
        self._render("\n".join(lines))
        self.where.setText("")
        for doc in seen:
            it = QListWidgetItem(doc[:-3])
            it.setData(Qt.ItemDataRole.UserRole,
                       next(i for i, s in enumerate(self.index) if s.doc == doc))
            self.hits.addItem(it)

    # ---- search ------------------------------------------------------------

    def _on_query(self, text):
        text = text.strip()
        if not text:
            self._show_contents()
            return
        terms = expand_query(text)
        found = search(self.index, text)
        self.hits.clear()
        self.count.setText(f"{len(found)} match(es)")
        if not found:
            self._render(
                f"# No match for \u201c{text}\u201d\n\n"
                "Try a single distinctive word: the name of a menu entry, a "
                "configuration key, a file extension, or an error message.")
            self.where.setText("")
            return
        for s in found:
            it = QListWidgetItem(f"{s.label}\n{snippet(s, terms)}")
            it.setData(Qt.ItemDataRole.UserRole, self.index.index(s))
            self.hits.addItem(it)
        self.hits.setCurrentRow(0)

    def _current_section(self):
        it = self.hits.currentItem()
        if it is None:
            return None
        i = it.data(Qt.ItemDataRole.UserRole)
        return self.index[i] if i is not None else None

    def _show_current(self, *_):
        s = self._current_section()
        if s is None:
            return
        self._show_document(s)
        self.where.setText(f"{s.doc}" + (f"  \u2014  {s.title}" if s.title else ""))

    def _open_in_browser(self):
        """Open the generated HTML page, building it first if it is missing."""
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices

        from ..docsgen import build_html_docs

        section = self._current_section()
        try:
            written = build_html_docs()
        except (FileNotFoundError, OSError) as exc:
            self.view.setHtml(markdown_to_html(
                f"# Cannot build the HTML documentation\n\n{exc}"))
            return
        out = written[0].parent
        target = out / "index.html"
        if section is not None:
            stem = section.doc[:-3] if section.doc.endswith(".md") else section.doc
            for candidate in (out / f"{stem}.html",
                              out / f"docs_{stem}.html"):
                if candidate.is_file():
                    target = candidate
                    break
        url = QUrl.fromLocalFile(str(target))
        if section is not None and section.anchor:
            url.setFragment(section.anchor)
        QDesktopServices.openUrl(url)
