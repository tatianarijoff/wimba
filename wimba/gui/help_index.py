"""Searchable in-application help, built from the project's own documentation.

The documentation is already written and kept current; this module makes it
reachable without leaving the application. It splits every Markdown file into
sections at its headings, and ranks those sections against what the user typed.

Two things make a plain substring search inadequate here, and both are handled:

* the vocabulary of the field is not the vocabulary of the documents -- someone
  looking for "excel" needs the page that says "spreadsheet", and someone
  typing "PEC" needs the passage about perfect conductors. :data:`ALIASES`
  bridges that gap;
* a hit in a heading means much more than a hit in a paragraph, so matches are
  weighted rather than counted.

The index is built from files on disk, so an edited document is reflected the
next time the browser is opened -- no rebuild step.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

#: Extra terms searched alongside what the user typed. Keys are what someone
#: might reasonably type; values are the words the documents actually use.
ALIASES = {
    "excel": ["spreadsheet", "xlsx", "precalculated"],
    "xls": ["spreadsheet", "xlsx"],
    "spreadsheet": ["xlsx", "precalculated"],
    "csv": ["export", "precalculated", "table"],
    "pec": ["perfect conductor", "boundary"],
    "boundary": ["pec", "vacuum", "layer"],
    "vacuum": ["boundary", "layer"],
    "ferrite": ["permeability", "susceptibility", "relaxation"],
    "permeability": ["muinf", "susceptibility", "relaxation"],
    "conductivity": ["sigma", "resistivity", "material"],
    "resistivity": ["sigma", "conductivity"],
    "grid": ["frequency", "fmin", "fmax", "fstep", "sampling"],
    "frequency": ["grid", "fmin", "fmax", "sampling"],
    "gamma": ["relativistic", "beam"],
    "beam": ["gamma", "beta", "optics"],
    "optics": ["twiss", "beta", "madx"],
    "twiss": ["optics", "madx", "tfs"],
    "wake": ["time domain", "fourier", "wakefield"],
    "space charge": ["isc", "dsc", "indirect", "direct"],
    "isc": ["indirect space charge"],
    "install": ["installation", "pip", "venv", "environment"],
    "error": ["troubleshooting", "not found", "fails"],
    "compare": ["comparison", "additional calculations"],
    "export": ["results", "csv", "txt", "save"],
    "data": ["optics", "data_dir", "external"],
    "missing": ["not found", "data_dir", "troubleshooting"],

}

#: Words too common to narrow anything down. Without these a question phrased as
#: a sentence matches most of the documentation.
STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are",
    "how", "do", "does", "did", "with", "from", "it", "its", "as", "at", "by",
    "be", "can", "no", "not", "but", "than", "then", "this", "that", "these",
    "those", "there", "here", "what", "when", "where", "which", "who", "why",
    "have", "has", "had", "will", "would", "should", "could", "about", "into",
    "over", "more", "most", "some", "any", "all", "such", "thing", "things",
    "they", "them", "their", "we", "you", "your", "my", "me", "also", "only",
    "very", "just", "get", "got", "make", "made", "use", "used", "using",
    "want", "need", "please", "one", "two", "same", "other", "each",
}

#: Files offered even though they sit outside docs/.
_EXTRA_DOCS = ("README.md",)


@dataclass
class Section:
    """One heading and the text under it."""
    doc: str                      # file name, e.g. "IW2D.md"
    title: str                    # heading text, "" for the preamble
    level: int                    # heading depth, 0 for the preamble
    body: str
    path: Path = field(repr=False, default=None)

    @property
    def anchor(self) -> str:
        """Where this section sits in its document, for scrolling to it."""
        from ..docsgen import _slug
        return _slug(self.title) if self.title else ""

    @property
    def label(self) -> str:
        stem = self.doc[:-3] if self.doc.endswith(".md") else self.doc
        return f"{stem} \u2014 {self.title}" if self.title else stem


def doc_roots(start=None):
    """Directories that may hold the documentation, most likely first.

    An editable install runs from the checkout, where ``docs/`` sits beside the
    package. A wheel install may carry a copy inside the package instead.
    """
    here = Path(start or __file__).resolve()
    pkg = here.parent.parent               # .../wimba
    return [pkg.parent / "docs", pkg / "docs", pkg.parent]


def find_docs(start=None):
    """Markdown files to index, or [] when the documentation is not present."""
    for root in doc_roots(start):
        if not root.is_dir():
            continue
        files = sorted(root.glob("*.md"))
        if root.name == "docs" and files:
            extra = [root.parent / n for n in _EXTRA_DOCS]
            return [f for f in extra if f.is_file()] + files
    return []


_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def split_sections(text: str, doc: str, path=None):
    """Split one Markdown document into :class:`Section` objects."""
    out, title, level, buf = [], "", 0, []
    in_code = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
        m = None if in_code else _HEADING.match(line)
        if m:
            if buf or title:
                out.append(Section(doc, title, level, "\n".join(buf).strip(), path))
            title, level, buf = m.group(2), len(m.group(1)), []
        else:
            buf.append(line)
    if buf or title:
        out.append(Section(doc, title, level, "\n".join(buf).strip(), path))
    return [s for s in out if s.title or s.body]


def build_index(start=None):
    """Every section of every documentation file."""
    index = []
    for path in find_docs(start):
        try:
            index.extend(split_sections(path.read_text(errors="replace"),
                                        path.name, path))
        except OSError:
            continue
    return index


def expand_query(query: str):
    """The user's words plus the documents' words for the same ideas."""
    q = query.lower().strip()
    # three characters is the shortest meaningful term here (PEC, ISC, CST);
    # anything shorter is noise
    terms = [t for t in re.split(r"[^\w+]+", q)
             if len(t) >= 3 and t not in STOPWORDS]
    extra = []
    for key, values in ALIASES.items():
        if key in q or key in terms:
            extra.extend(values)
    seen, out = set(), []
    for t in terms + extra:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def score(section: Section, terms) -> int:
    """How well one section answers the query.

    A term in the heading counts for much more than one in the body: headings
    are what the document is about, paragraphs merely mention things.
    """
    if not terms:
        return 0
    title, body = section.title.lower(), section.body.lower()
    total = 0
    for t in terms:
        in_title = title.count(t)
        in_body = body.count(t)
        if in_title:
            total += 20 * in_title
        if in_body:
            total += min(in_body, 5)
    # a section matching several distinct terms is a better answer than one
    # repeating a single term
    distinct = sum(1 for t in terms if t in title or t in body)
    return total + 10 * max(0, distinct - 1)


def search(index, query, limit=25):
    """Sections answering ``query``, best first."""
    terms = expand_query(query)
    if not terms:
        return []
    scored = [(score(s, terms), s) for s in index]
    scored = [(n, s) for n, s in scored if n > 0]
    scored.sort(key=lambda p: (-p[0], p[1].doc, p[1].title))
    return [s for _n, s in scored[:limit]]


def snippet(section: Section, terms, width=160) -> str:
    """A line of context around the first match, for the results list."""
    body = " ".join(section.body.split())
    low = body.lower()
    pos = min((low.find(t) for t in terms if low.find(t) >= 0), default=-1)
    if pos < 0:
        return body[:width] + ("\u2026" if len(body) > width else "")
    start = max(0, pos - width // 3)
    text = body[start:start + width]
    return ("\u2026" if start else "") + text + ("\u2026" if start + width < len(body) else "")

