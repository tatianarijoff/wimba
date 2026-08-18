"""Render the project's Markdown documentation as HTML.

Two users, one converter:

* the in-application help, which renders a section at a time into a
  ``QTextBrowser``. Qt reads Markdown but drops tables -- and the documentation
  is largely tables -- so it is given HTML instead;
* :func:`build_html_docs`, which writes a browsable ``docs/html/`` for reading
  or publishing outside the application.

The converter is written here rather than taken from a library so that the help
works in any environment WIMBA runs in, with no external program and no extra
dependency. It covers the Markdown the documentation actually uses: headings,
paragraphs, fenced and inline code, emphasis, links, images, ordered and
unordered lists, tables, block quotes and horizontal rules.
"""
from __future__ import annotations

import html as _html
import re
import shutil
from pathlib import Path

#: Stylesheet used by both the generated files and the in-application help.
#: Qt supports a subset of CSS, so this stays deliberately plain.
STYLESHEET = """
body      { font-family: sans-serif; font-size: 10.5pt; line-height: 1.45;
            color: #1c1c1c; background: #ffffff; margin: 18px 24px; }
h1        { font-size: 20pt; margin: 0 0 12px 0; color: #123a5c; }
h2        { font-size: 15pt; margin: 22px 0 8px 0; color: #123a5c;
            border-bottom: 1px solid #d5dde4; padding-bottom: 3px; }
h3        { font-size: 12.5pt; margin: 18px 0 6px 0; color: #1a4d7a; }
h4, h5, h6{ font-size: 11pt; margin: 14px 0 4px 0; color: #1a4d7a; }
p         { margin: 8px 0; }
a         { color: #1665a6; text-decoration: none; }
code      { font-family: monospace; background: #f2f4f6; color: #8a2b2b;
            padding: 1px 3px; }
pre       { font-family: monospace; background: #f6f8fa; color: #24292e;
            border: 1px solid #dfe3e8; padding: 9px 11px; margin: 10px 0; }
pre code  { background: transparent; color: #24292e; padding: 0; }
table     { border-collapse: collapse; margin: 12px 0; }
th        { background: #eef2f6; border: 1px solid #c8d2dc; padding: 5px 10px;
            text-align: left; font-weight: bold; }
td        { border: 1px solid #d8e0e8; padding: 5px 10px; }
blockquote{ border-left: 3px solid #c8d2dc; background: #f7f9fb;
            margin: 10px 0; padding: 6px 12px; color: #33444f; }
hr        { border: none; border-top: 1px solid #d5dde4; margin: 18px 0; }
ul, ol    { margin: 8px 0 8px 22px; }
li        { margin: 3px 0; }
img       { margin: 8px 0; }
.doc-nav  { color: #5a6b78; font-size: 9.5pt; margin-bottom: 14px; }
"""

#: Tags passed through from the source instead of being escaped. Markdown
#: allows inline HTML and the documentation uses it for things Markdown cannot
#: express -- a centred logo, an image with a width. Everything outside this
#: list is escaped: documentation is text, not markup to execute.
ALLOWED_TAGS = {
    "p", "br", "hr", "div", "span", "center", "em", "strong", "b", "i", "u",
    "small", "sub", "sup", "code", "pre", "kbd", "a", "img", "figure",
    "figcaption", "blockquote", "table", "thead", "tbody", "tr", "th", "td",
    "ul", "ol", "li", "dl", "dt", "dd", "h1", "h2", "h3", "h4", "h5", "h6",
    "details", "summary", "abbr",
}

_ALLOWED_ESCAPED = re.compile(
    r"&lt;(/?)(" + "|".join(sorted(ALLOWED_TAGS)) + r")\b([^&]*?)/?&gt;",
    re.I)
_ENTITY = re.compile(r"&amp;(#?\w+);")
_BLOCK_HTML = re.compile(
    r"^\s*</?(" + "|".join(sorted(ALLOWED_TAGS)) + r")\b", re.I)

#: Full stylesheet for the generated pages. The one above is the subset Qt
#: understands; this one is for a browser, where a sidebar and a fixed layout
#: are possible.
WEB_STYLESHEET = """
:root {
  --ink:#1c2530; --muted:#5d6f7f; --line:#dde4ea; --accent:#1665a6;
  --deep:#0f3557; --bg:#ffffff; --soft:#f6f8fa; --side:#12283d;
}
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
       font-family:-apple-system,"Segoe UI",Roboto,"Helvetica Neue",sans-serif;
       font-size:15px; line-height:1.62; }

/* ---- sidebar ---- */
.sidebar { position:fixed; top:0; left:0; width:264px; height:100vh;
           background:var(--side); color:#c9d6e2; overflow-y:auto; }
.sidebar-header { padding:18px 20px 14px; border-bottom:1px solid #21405c; }
.sidebar-logo-link { color:#fff; font-size:19px; font-weight:600;
                     text-decoration:none; letter-spacing:.4px; }
.sidebar-logo-link img { display:block; max-width:170px; margin-bottom:9px; }
.sidebar-sub { color:#7f9cb5; font-size:11.5px; margin-top:3px; }
.sidebar-nav { padding:10px 0 40px; }
.nav-section { margin:2px 0; }
.nav-section-header { display:flex; align-items:center; justify-content:space-between;
                      padding:8px 20px; cursor:pointer; user-select:none; }
.nav-section-header:hover { background:#1a3550; }
.nav-section-title { font-size:12px; letter-spacing:.9px; text-transform:uppercase;
                     color:#8fb0cb; font-weight:600; }
.nav-toggle-icon { width:0; height:0; border-left:4px solid #8fb0cb;
                   border-top:4px solid transparent; border-bottom:4px solid transparent;
                   transform:rotate(90deg); transition:transform .15s; }
.nav-section.collapsed .nav-toggle-icon { transform:rotate(0deg); }
.nav-section.collapsed .nav-section-content { display:none; }
.nav-section-content { list-style:none; margin:0; padding:0 0 6px; }
.nav-section-content li a { display:block; padding:5px 20px 5px 30px;
                            color:#c9d6e2; text-decoration:none; font-size:13.5px; }
.nav-section-content li a:hover { background:#1b3a58; color:#fff; }
.nav-section-content li a.current { background:#1f4a70; color:#fff;
                                    border-left:3px solid var(--accent);
                                    padding-left:27px; font-weight:600; }

/* ---- content ---- */
.content { margin-left:264px; padding:34px 46px 90px; max-width:1000px; }
#title-block-header { border-bottom:2px solid var(--line); margin-bottom:26px;
                      padding-bottom:14px; }
.title-with-logo { display:flex; align-items:center; justify-content:space-between;
                   gap:20px; }
h1.title { font-size:29px; margin:0; color:var(--deep); }
.header-logo { max-height:46px; opacity:.9; }
.doc-nav { color:var(--muted); font-size:12.5px; margin:0 0 4px; }
.doc-nav a { color:var(--accent); text-decoration:none; }

h1 { font-size:26px; color:var(--deep); margin:30px 0 12px; }
h2 { font-size:20px; color:var(--deep); margin:32px 0 10px;
     border-bottom:1px solid var(--line); padding-bottom:5px; }
h3 { font-size:16.5px; color:#1a4d7a; margin:24px 0 8px; }
h4,h5,h6 { font-size:14.5px; color:#1a4d7a; margin:18px 0 6px; }
p { margin:11px 0; }
a { color:var(--accent); }
ul,ol { margin:10px 0 10px 24px; }
li { margin:4px 0; }
hr { border:none; border-top:1px solid var(--line); margin:26px 0; }
img { max-width:100%; }

code { font-family:"SF Mono",Menlo,Consolas,monospace; font-size:13px;
       background:var(--soft); color:#a03030; padding:2px 5px; border-radius:3px; }
pre { background:#f8fafc; border:1px solid var(--line); border-left:3px solid var(--accent);
      padding:13px 16px; margin:14px 0; overflow-x:auto; border-radius:3px; }
pre code { background:none; color:#24292e; padding:0; font-size:13px; line-height:1.5; }
pre .k { color:#0f7020; font-weight:600; }
pre .s { color:#a03030; }
pre .c { color:#7a8a97; font-style:italic; }
pre .n { color:#1665a6; }

table { border-collapse:collapse; margin:16px 0; font-size:14px; }
th { background:#eef3f8; border:1px solid #cbd7e2; padding:7px 13px;
     text-align:left; color:var(--deep); font-weight:600; }
td { border:1px solid var(--line); padding:7px 13px; vertical-align:top; }
tr.odd td { background:#fafbfc; }

blockquote { border-left:4px solid #f0b429; background:#fffaf0; margin:14px 0;
             padding:10px 16px; color:#5b4a26; }
blockquote p:first-child { margin-top:0; }
blockquote p:last-child { margin-bottom:0; }

.toc { background:var(--soft); border:1px solid var(--line); border-radius:4px;
       padding:12px 18px; margin:0 0 26px; font-size:13.5px; }
.toc-title { font-weight:600; color:var(--deep); margin-bottom:6px;
             text-transform:uppercase; letter-spacing:.7px; font-size:11.5px; }
.toc ul { list-style:none; margin:0; padding:0; }
.toc li { margin:3px 0; }
.toc li.lvl3 { padding-left:18px; font-size:13px; }
.toc a { text-decoration:none; }

@media (max-width:900px) {
  .sidebar { position:static; width:auto; height:auto; }
  .content { margin-left:0; padding:22px; }
}
"""

#: Collapsible sidebar sections.
SIDEBAR_JS = """
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.nav-section-header').forEach(function (h) {
    h.addEventListener('click', function () {
      h.parentElement.classList.toggle('collapsed');
    });
  });
  var current = document.querySelector('.nav-section-content a.current');
  if (current) {
    var sec = current.closest('.nav-section');
    if (sec) { sec.classList.remove('collapsed'); }
  }
});
"""

#: Sidebar grouping. Files not listed fall into "Other".
SECTIONS = (
    ("Getting started", ("README", "SETUP", "SETTINGS", "EXAMPLES")),
    ("Workflows", ("GUI", "PROJECTS", "ASSEMBLE_AND_RUN", "BUILD", "COMPONENT")),
    ("Engines", ("PYTLWALL_CFG", "IW2D", "RESONATOR", "PRECALCULATED",
                 "FOURIER")),
    ("Reference", ("CONFIG", "DATA_MODEL", "DATA", "docs_README")),
)

_KEYWORDS = {
    "python": ("and as assert async await break class continue def del elif else "
               "except finally for from global if import in is lambda nonlocal "
               "not or pass raise return try while with yield None True False "
               "self").split(),
    "bash": ("if then else fi for while do done case esac function return export "
             "source cd echo exit local set unset").split(),
    "yaml": (),
}

def _highlight(code: str, lang: str) -> str:
    """Colour a code block: comments, strings, numbers, keywords.

    One pass over the source, emitting escaped text and spans as it goes.
    Highlighting in several passes would re-process the markup it had just
    inserted -- the attribute of a span becoming a keyword inside another span.

    Deliberately shallow: enough to read a snippet, not a parser.
    """
    words = _KEYWORDS.get((lang or "").lower(), ())
    kw = r"\b(?:" + "|".join(words) + r")\b" if words else r"(?!x)x"
    pattern = re.compile(
        r"(?P<c>#[^\n]*)"
        r"|(?P<s>'[^'\n]*'|\"[^\"\n]*\")"
        r"|(?P<n>\b\d+\.?\d*(?:[eE][-+]?\d+)?\b)"
        r"|(?P<k>" + kw + r")")
    out, last = [], 0
    for m in pattern.finditer(code):
        out.append(_html.escape(code[last:m.start()]))
        out.append(f'<span class="{m.lastgroup}">{_html.escape(m.group())}</span>')
        last = m.end()
    out.append(_html.escape(code[last:]))
    return "".join(out)


def _slug(text: str) -> str:
    """Heading anchor, as a reader would guess it."""
    s = re.sub(r"<[^>]+>", "", text).lower()
    s = re.sub(r"[^\w\s-]", "", s)
    return re.sub(r"[\s_]+", "-", s).strip("-") or "section"


_H = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_HR = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
_UL = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_OL = re.compile(r"^(\s*)\d+[.)]\s+(.*)$")
_QUOTE = re.compile(r"^\s*>\s?(.*)$")
# a separator row: dashes and optional colons. At least one pipe is required,
# so a plain horizontal rule cannot be mistaken for one, and a single-column
# table is still recognised.
_TABLE_SEP = re.compile(
    r"^(?=[^|]*\|)\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def _inline(text: str) -> str:
    """Inline markup of one line, escaping everything else."""
    out, last = [], 0
    # code spans first: their content must not be interpreted further
    for m in re.finditer(r"`([^`]+)`", text):
        out.append(_inline_no_code(text[last:m.start()]))
        out.append(f"<code>{_html.escape(m.group(1))}</code>")
        last = m.end()
    out.append(_inline_no_code(text[last:]))
    return "".join(out)


def _inline_no_code(text: str) -> str:
    s = _html.escape(text)
    s = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)[^)]*\)",
               lambda m: f'<img src="{m.group(2)}" alt="{m.group(1)}">', s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)[^)]*\)",
               lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"__([^_]+)__", r"<b>\1</b>", s)
    s = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?!\w)", r"<i>\1</i>", s)
    return _unescape_allowed(s)


def _unescape_allowed(s: str) -> str:
    """Give back the tags on the allowlist, and the entities they carry."""
    s = _ALLOWED_ESCAPED.sub(
        lambda m: f"<{m.group(1)}{m.group(2)}{_html.unescape(m.group(3))}>", s)
    return _ENTITY.sub(r"&\1;", s)


def _split_row(line: str):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def markdown_to_html(text: str, body_only: bool = True, title: str = "") -> str:
    """Convert Markdown to HTML.

    Args:
        text: the Markdown source.
        body_only: return only the body, for embedding in a widget; otherwise a
            complete document with the stylesheet inlined.
        title: document title, used when ``body_only`` is False.

    Returns:
        HTML markup.
    """
    lines = text.splitlines()
    out, i, n = [], 0, len(lines)
    para: list = []

    def flush():
        if para:
            out.append("<p>" + "<br>".join(_inline(p) for p in para) + "</p>")
            para.clear()

    while i < n:
        line = lines[i]

        if line.lstrip().startswith("```"):
            flush()
            lang = line.lstrip()[3:].strip()
            i += 1
            block = []
            while i < n and not lines[i].lstrip().startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1
            cls = f' class="lang-{_html.escape(lang)}"' if lang else ""
            out.append(f"<pre{cls}><code>" +
                       _highlight("\n".join(block), lang) + "</code></pre>")
            continue

        if not line.strip():
            flush()
            i += 1
            continue

        # a block of raw HTML: pass it through as written, up to a blank line or
        # the first Markdown block that follows it. Documents often put a
        # centred logo immediately above the title, with no blank line between,
        # and the title must still be a heading.
        if _BLOCK_HTML.match(line):
            flush()
            block = []
            while i < n and lines[i].strip():
                if block and (_H.match(lines[i])
                              or lines[i].lstrip().startswith("```")):
                    break
                block.append(lines[i])
                i += 1
            out.append("\n".join(block))
            continue

        if _HR.match(line):
            flush()
            out.append("<hr>")
            i += 1
            continue

        m = _H.match(line)
        if m:
            flush()
            level = len(m.group(1))
            inner = _inline(m.group(2))
            anc = _slug(m.group(2))
            # both forms: id for a browser, <a name> for Qt's scrollToAnchor
            out.append(f'<h{level} id="{anc}">'
                       f'<a name="{anc}"></a>{inner}</h{level}>')
            i += 1
            continue

        # table: a header row followed by a separator row
        if "|" in line and i + 1 < n and _TABLE_SEP.match(lines[i + 1]):
            flush()
            head = _split_row(line)
            i += 2
            rows = []
            while i < n and lines[i].strip() and "|" in lines[i]:
                rows.append(_split_row(lines[i]))
                i += 1
            cells = "".join(f"<th>{_inline(c)}</th>" for c in head)
            body = ""
            for k, r in enumerate(rows):
                r = (r + [""] * len(head))[:len(head)]
                cls = ' class="odd"' if k % 2 else ""
                body += f"<tr{cls}>" + "".join(f"<td>{_inline(c)}</td>"
                                               for c in r) + "</tr>"
            out.append(f"<table><tr>{cells}</tr>{body}</table>")
            continue

        if _QUOTE.match(line):
            flush()
            block = []
            while i < n and _QUOTE.match(lines[i]):
                block.append(_QUOTE.match(lines[i]).group(1))
                i += 1
            out.append("<blockquote>" +
                       markdown_to_html("\n".join(block)) + "</blockquote>")
            continue

        if _UL.match(line) or _OL.match(line):
            flush()
            ordered = bool(_OL.match(line))
            tag = "ol" if ordered else "ul"
            items = []
            while i < n:
                m2 = _OL.match(lines[i]) if ordered else _UL.match(lines[i])
                if m2:
                    items.append(_inline(m2.group(2)))
                    i += 1
                elif lines[i].strip() and lines[i].startswith((" ", "\t")):
                    if items:                       # continuation of an item
                        items[-1] += " " + _inline(lines[i].strip())
                    i += 1
                else:
                    break
            out.append(f"<{tag}>" + "".join(f"<li>{it}</li>" for it in items) +
                       f"</{tag}>")
            continue

        para.append(line.strip())
        i += 1

    flush()
    body = "\n".join(out)
    if body_only:
        return body
    return (f"<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\">"
            f"<title>{_html.escape(title)}</title>"
            f"<style>{STYLESHEET}</style></head><body>\n{body}\n</body></html>")


# ---------------------------------------------------------------------------
# Building a browsable docs/html/
# ---------------------------------------------------------------------------

def _rewrite_doc_links(body: str, renamed=None) -> str:
    """Point links between documents at the generated HTML.

    ``renamed`` maps a source stem to the page it was written as, for the
    documents that had to be disambiguated.
    """
    renamed = renamed or {}

    def repl(m):
        stem = m.group(1).rsplit("/", 1)[-1]
        return f'href="{renamed.get(stem, stem)}.html{m.group(2) or ""}"'

    return re.sub(r'href="([^"]+)\.md(#[^"]*)?"', repl, body)


def _images_in(text: str):
    """Image references, both Markdown and <img src="...">."""
    for m in re.finditer(r"!\[[^\]]*\]\(([^)\s]+)", text):
        yield m.group(1)
    for m in re.finditer(r"<img\s[^>]*src\s*=\s*[\"\']([^\"\']+)", text, re.I):
        yield m.group(1)


def _headings(text: str):
    """(level, title, anchor) for the h2/h3 of one document, for its contents."""
    out, in_code = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = _H.match(line)
        if m and 2 <= len(m.group(1)) <= 3:
            out.append((len(m.group(1)), m.group(2), _slug(m.group(2))))
    return out


def _sidebar(pages, current, logo=None):
    """The navigation column, grouped as :data:`SECTIONS`."""
    by_stem = {stem: (href, title) for stem, href, title in pages}
    placed, blocks = set(), []
    for name, stems in SECTIONS:
        items = [(s_, *by_stem[s_]) for s_ in stems if s_ in by_stem]
        if not items:
            continue
        placed.update(s_ for s_, _h, _t in items)
        blocks.append((name, items))
    rest = [(s_, *by_stem[s_]) for s_ in by_stem if s_ not in placed]
    if rest:
        blocks.append(("Other", sorted(rest)))

    parts = []
    for name, items in blocks:
        open_here = any(st == current for st, _h, _t in items)
        cls = "nav-section" if open_here else "nav-section collapsed"
        def _item(st, h, t):
            # the class attribute is built outside the f-string: Python
            # before 3.12 does not allow a backslash in an f-string
            mark = ' class="current"' if st == current else ""
            return f'<li><a href="{h}"{mark}>{_html.escape(t)}</a></li>'

        lis = "".join(_item(st, h, t) for st, h, t in items)
        parts.append(
            f'<div class="{cls}" data-section="{_slug(name)}">'
            f'<div class="nav-section-header">'
            f'<span class="nav-section-title">{_html.escape(name)}</span>'
            f'<span class="nav-toggle-icon"></span></div>'
            f'<ul class="nav-section-content">{lis}</ul></div>')

    brand = (f'<img src="{logo}" alt="WIMBA">' if logo else "WIMBA")
    return (f'<aside class="sidebar">'
            f'<div class="sidebar-header">'
            f'<a href="index.html" class="sidebar-logo-link">{brand}</a>'
            f'<div class="sidebar-sub">Wake &amp; Impedance Model Builder'
            f'<br>for Accelerators</div></div>'
            f'<nav class="sidebar-nav">{"".join(parts)}</nav></aside>')


def _page(title, source_name, body, sidebar, toc, logo=None):
    head_logo = (f'<img src="{logo}" alt="" class="header-logo">' if logo else "")
    return (f'<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{_html.escape(title)} \u2014 WIMBA</title>'
            f'<link rel="stylesheet" href="style.css"></head><body>\n'
            f'{sidebar}\n<main class="content">\n'
            f'<header id="title-block-header">'
            f'<p class="doc-nav"><a href="index.html">Documentation</a>'
            f' &nbsp;\u203a&nbsp; {_html.escape(source_name)}</p>'
            f'<div class="title-with-logo"><h1 class="title">'
            f'{_html.escape(title)}</h1>{head_logo}</div></header>\n'
            f'{toc}\n{body}\n</main>\n'
            f'<script src="sidebar.js"></script></body></html>')


def build_html_docs(source=None, out_dir=None, extra=("README.md",)) -> list:
    """Write the documentation as a browsable HTML folder.

    Each page carries a navigation sidebar grouped as :data:`SECTIONS`, a
    header, and a contents list built from its own headings. Code blocks are
    highlighted and links between documents are rewritten to the generated
    pages.

    Args:
        source: the ``docs/`` directory; found next to the package if omitted.
        out_dir: destination, ``<source>/html`` by default.
        extra: files outside ``source`` to include, relative to its parent.

    Returns:
        The paths written, index first.

    Raises:
        FileNotFoundError: the documentation directory does not exist.
    """
    from .gui.help_index import doc_roots

    src = Path(source) if source else next(
        (r for r in doc_roots() if r.is_dir() and r.name == "docs"), None)
    if src is None or not src.is_dir():
        raise FileNotFoundError(
            "the docs/ directory was not found; pass source= explicitly.")
    out = Path(out_dir) if out_dir else src / "html"
    out.mkdir(parents=True, exist_ok=True)

    files = [src.parent / e for e in extra if (src.parent / e).is_file()]
    files += sorted(p for p in src.glob("*.md"))

    (out / "style.css").write_text(WEB_STYLESHEET.strip() + "\n")
    (out / "sidebar.js").write_text(SIDEBAR_JS.strip() + "\n")
    written = [out / "style.css", out / "sidebar.js"]

    # first pass: names, titles, images
    docs, used, renamed = [], {}, {}
    logo = None
    for md in files:
        text = md.read_text(errors="replace")
        first = next((l for l in text.splitlines() if l.startswith("# ")), "")
        title = first[2:].strip() or md.stem
        stem = md.stem if md.stem not in used else f"{md.parent.name}_{md.stem}"
        if stem != md.stem:
            renamed[md.stem] = stem
        used[stem] = md

        images = {}
        for ref in _images_in(text):
            if ref.startswith(("http://", "https://", "data:")):
                continue
            img = (md.parent / ref).resolve()
            if img.is_file():
                target = out / img.name
                shutil.copy2(img, target)
                images[ref] = img.name
                if target not in written:
                    written.append(target)
                if logo is None and "logo" in img.name.lower():
                    logo = img.name
        docs.append((stem, md, text, title, images))

    pages = [(stem, stem + ".html", title) for stem, _m, _t, title, _i in docs]

    # second pass: render
    for stem, md, text, title, images in docs:
        body = _rewrite_doc_links(markdown_to_html(text), renamed)
        for ref, name in images.items():
            body = body.replace(f'src="{ref}"', f'src="{name}"')

        heads = _headings(text)
        toc = ""
        if len(heads) > 2:
            items = "".join(
                f'<li class="lvl{lv}"><a href="#{anc}">{_html.escape(t)}</a></li>'
                for lv, t, anc in heads)
            toc = (f'<div class="toc"><div class="toc-title">On this page</div>'
                   f'<ul>{items}</ul></div>')

        (out / (stem + ".html")).write_text(
            _page(title, md.name, body, _sidebar(pages, stem, logo), toc, logo))
        written.append(out / (stem + ".html"))

    def _row(k, st, h, t):
        mark = ' class="odd"' if k % 2 else ""
        return (f'<tr{mark}><td><a href="{h}">{_html.escape(t)}</a></td>'
                f'<td><code>{_html.escape(st)}.md</code></td></tr>')

    rows = "".join(_row(k, st, h, t) for k, (st, h, t) in enumerate(pages))
    index_body = (f'<p>Generated from the Markdown sources with '
                  f'<code>wimba docs</code>. The sources remain the originals.</p>'
                  f'<table><tr><th>Page</th><th>Source</th></tr>{rows}</table>')
    (out / "index.html").write_text(
        _page("WIMBA documentation", "index", index_body,
              _sidebar(pages, "", logo), "", logo))
    return [out / "index.html"] + written
