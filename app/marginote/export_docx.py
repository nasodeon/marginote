"""The Word file of an export: the same document as the PDF. Every part has a named style (Citation, Référence,
Note…), so changing one style in Word changes all of them. The contents at the top is a real Word table of
contents: its lines link to their headings from the start, and Word adds the page numbers when it opens the file
(it asks to update the fields)."""

import io

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from docx.text.paragraph import Paragraph

FONT = "Cambria"            # comes with Word on Windows and Mac (Computer Modern does not)
BLACK, GREY = RGBColor(0, 0, 0), RGBColor(0x63, 0x63, 0x63)
LANG = {"fr": "fr-FR", "en": "en-GB"}
WIDTH = Cm(21 - 2 * 2.6)


def _el(tag: str, **attrs) -> OxmlElement:
    e = OxmlElement(tag)
    for k, v in attrs.items():
        e.set(qn(k), str(v))
    return e


def _field_char(kind: str) -> OxmlElement:
    r = _el("w:r")
    r.append(_el("w:fldChar", **{"w:fldCharType": kind}))
    return r


def _instr(code: str) -> OxmlElement:
    r, t = _el("w:r"), _el("w:instrText", **{"xml:space": "preserve"})
    t.text = f" {code} "
    r.append(t)
    return r


def _runs(par: Paragraph, runs: list) -> None:
    for text, italic in runs:
        r = par.add_run(text)
        if italic:
            r.italic = True


def _left_rule(par: Paragraph) -> None:
    border = _el("w:pBdr")
    border.append(_el("w:left", **{"w:val": "single", "w:sz": 4, "w:space": 8, "w:color": "B5B5B5"}))
    par._p.get_or_add_pPr().append(border)


def _shade(par: Paragraph) -> None:
    par._p.get_or_add_pPr().append(_el("w:shd", **{"w:val": "clear", "w:color": "auto", "w:fill": "F2F2F2"}))


class _Writer:
    def __init__(self, doc_data: dict) -> None:
        self.data, self.L = doc_data, doc_data["labels"]
        self.d = Document()
        self.marks: list[tuple[int, list, str]] = []
        self._setup()
        self.ids = {st.name: st.style_id for st in self.d.styles}
        self.end = self.d.element.body.find(qn("w:sectPr"))

    def para(self, style: str | None = None, text: str | None = None) -> Paragraph:
        """A new paragraph at the end, in a style. Put in place directly: python-docx's own way looks through the
        whole document and every style for each paragraph (3,000 quotes took 8 seconds)."""
        el = _el("w:p")
        self.end.addprevious(el)              # the section's settings close the body
        p = Paragraph(el, self.d._body)
        if style:
            p._p.get_or_add_pPr().style = self.ids[style]
        if text:
            p.add_run(text)
        return p

    # ----- page and styles -----

    def _style(self, name, base="Normal", size=None, italic=None, bold=None, color=BLACK, align=None, before=None,
               after=None, left=None, keep=False, small_caps=None):
        try:
            st = self.d.styles[name]
        except KeyError:
            st = self.d.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
            st.base_style = self.d.styles[base]
        f, pf = st.font, st.paragraph_format
        f.name = FONT
        fonts = st.element.get_or_add_rPr().find(qn("w:rFonts"))
        for theme in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):   # or Word's theme font wins
            if fonts is not None and fonts.get(qn(theme)) is not None:
                del fonts.attrib[qn(theme)]
        if size:
            f.size = Pt(size)
        if italic is not None:
            f.italic = italic
        if bold is not None:
            f.bold = bold
        if small_caps is not None:
            f.small_caps = small_caps
        f.color.rgb = color
        if align is not None:
            pf.alignment = align
        if before is not None:
            pf.space_before = Pt(before)
        if after is not None:
            pf.space_after = Pt(after)
        if left is not None:
            pf.left_indent = Cm(left)
        pf.keep_with_next = keep
        return st

    def _setup(self) -> None:
        d = self.d
        sec = d.sections[0]
        sec.page_width, sec.page_height = Cm(21), Cm(29.7)
        sec.left_margin = sec.right_margin = Cm(2.6)
        sec.top_margin, sec.bottom_margin = Cm(2.6), Cm(2.4)
        normal = d.styles["Normal"]
        normal.font.name, normal.font.size = FONT, Pt(11)
        normal.element.get_or_add_rPr().append(_el("w:lang", **{"w:val": LANG.get(self.data["lang"], "fr-FR")}))
        normal.paragraph_format.space_after = Pt(6)
        normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        d.settings.element.append(_el("w:autoHyphenation"))
        d.settings.element.append(_el("w:updateFields", **{"w:val": "true"}))
        self._style("Title", size=26, after=2)
        d.styles["Title"].element.get_or_add_pPr().remove_all("w:pBdr")
        self._style("Subtitle", size=13, italic=True, after=2)
        self._style("Heading 1", size=18, bold=False, before=26, after=2, keep=True)
        self._style("Heading 2", size=13, bold=False, italic=False, before=16, after=1, keep=True)
        self._style("Heading 3", size=11.5, bold=False, italic=False, before=12, after=1, keep=True)
        self._style("Marginote — étiquette", size=10.5, small_caps=True, color=GREY, before=18, after=4, keep=True,
                    align=WD_ALIGN_PARAGRAPH.LEFT)
        self._style("Marginote — détails", size=9.5, color=GREY, after=8, keep=True, align=WD_ALIGN_PARAGRAPH.LEFT)
        self._style("Quote", size=11, italic=False, before=10, after=2, left=0.5)
        self._style("Référence", size=9.5, align=WD_ALIGN_PARAGRAPH.RIGHT, after=1, left=0.5)
        self._style("Thèmes", size=8.5, color=GREY, after=1, left=0.5, align=WD_ALIGN_PARAGRAPH.LEFT)
        self._style("Commentaire", size=9.5, italic=True, after=4, left=0.5)
        self._style("Note — titre", size=10, before=10, after=2, left=0.25, keep=True, align=WD_ALIGN_PARAGRAPH.LEFT)
        self._style("Note", size=11, after=3, left=0.25)
        bib = self._style("Bibliographie", size=11, after=4, left=0.8, align=WD_ALIGN_PARAGRAPH.LEFT)
        bib.paragraph_format.first_line_indent = Cm(-0.8)
        for level in (1, 2):
            st = self._style(f"toc {level}", size=11 if level == 1 else 10, after=2, left=0.6 * (level - 1),
                             align=WD_ALIGN_PARAGRAPH.LEFT, before=6 if level == 1 else 0)
            st.paragraph_format.tab_stops.add_tab_stop(WIDTH, WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
        footer = sec.footer.paragraphs[0]
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for part in (_field_char("begin"), _instr("PAGE"), _field_char("separate"), _field_char("end")):
            footer._p.append(part)

    # ----- parts -----

    def heading(self, level: int, runs: list, outlined: bool) -> Paragraph:
        p = self.para(f"Heading {level}")
        if outlined:
            n = len(self.marks)
            name = f"_Toc_m{n}"
            p._p.append(_el("w:bookmarkStart", **{"w:id": n, "w:name": name}))
            _runs(p, runs)
            p._p.append(_el("w:bookmarkEnd", **{"w:id": n}))
            self.marks.append((level, runs, name))
        else:
            _runs(p, runs)
        return p

    def quote(self, q: dict) -> None:
        d = self.d
        p = self.para("Quote")
        p.add_run(f"{self.L['open']}{q['text']}{self.L['close']}")
        p.paragraph_format.keep_with_next = True
        _left_rule(p)
        p = self.para("Référence")
        _runs(p, q["ref"])
        _left_rule(p)
        if q["topics"]:
            _left_rule(self.para("Thèmes", "  ·  ".join(q["topics"])))
        if q["comment"]:
            p = self.para("Commentaire")
            label = p.add_run(f"{self.L['comment']} — ")
            label.italic, label.font.small_caps = False, True
            p.add_run(q["comment"])
            _left_rule(p)

    def note(self, n: dict) -> None:
        d = self.d
        p = self.para("Note — titre")
        _shade(p)
        p.add_run(self.L["note"]).font.small_caps = True
        if n["title"]:
            p.add_run(" — ")
            p.add_run(n["title"]).bold = True
        if n["place"]:
            r = p.add_run("\t" + n["place"])
            r.font.size, r.font.color.rgb = Pt(9), GREY
            p.paragraph_format.tab_stops.add_tab_stop(WIDTH - Cm(0.5), WD_TAB_ALIGNMENT.RIGHT)
        for para in n["paras"]:
            _shade(self.para("Note", para))
        if n["topics"]:
            p = self.para("Thèmes", "  ·  ".join(n["topics"]))
            p.paragraph_format.left_indent = Cm(0.25)
            _shade(p)
        self.para().paragraph_format.space_after = Pt(0)

    def contents(self, first: Paragraph) -> None:
        """Fill the table of contents: a TOC field whose lines already link to the headings."""
        if not self.marks:
            return
        p, last = first, len(self.marks) - 1
        for k, (level, runs, name) in enumerate(self.marks):
            if k:
                new = _el("w:p")
                p._p.addnext(new)
                p = Paragraph(new, first._parent)
            p._p.get_or_add_pPr().style = self.ids[f"toc {min(level, 2)}"]
            if k == 0:
                for part in (_field_char("begin"), _instr('TOC \\o "1-2" \\h \\z \\u'), _field_char("separate")):
                    p._p.append(part)
            link = _el("w:hyperlink", **{"w:anchor": name, "w:history": 1})
            for text, italic in runs:
                r, rpr = _el("w:r"), _el("w:rPr")
                if italic:
                    rpr.append(_el("w:i"))
                r.append(rpr)
                t = _el("w:t", **{"xml:space": "preserve"})
                t.text = text
                r.append(t)
                link.append(r)
            p._p.append(link)
            if k == last:
                p._p.append(_field_char("end"))

    # ----- the document -----

    def write(self) -> bytes:
        d, data, L = self.d, self.data, self.L
        p = self.para("Marginote — détails")
        p.add_run("MARGINOTE").font.size = Pt(8.5)
        self.para("Title", data["title"])
        self.para("Subtitle", data["subtitle"])
        self.para("Marginote — détails", data["byline"])
        self.para("Marginote — étiquette", L["contents"])
        toc = self.para()                  # filled once every heading is known
        self.para().add_run().add_break(WD_BREAK.PAGE)
        for c in data["chapters"]:
            self.heading(1, c["title"], True)
            if c["meta"]:
                self.para("Marginote — détails", c["meta"])
            for s in c["sections"]:
                if s["label"]:
                    if s["outlined"]:
                        h = self.heading(2, [[s["label"], False]], True)
                        for r in h.runs:
                            r.font.small_caps, r.font.color.rgb, r.font.size = True, GREY, Pt(10.5)
                    else:
                        self.para("Marginote — étiquette", s["label"])
                for g in s["groups"]:
                    if g["head"]:
                        self.heading(g["level"], [[g["head"]["title"], True]], g["level"] == 2)
                        meta = (g["head"]["subtitle"] + "\n" if g["head"]["subtitle"] else "") + g["head"]["meta"]
                        if meta:
                            self.para("Marginote — détails", meta)
                    for item in g["items"]:
                        self.quote(item) if item["type"] == "quote" else self.note(item)
        if data["bibliography"]:
            self.heading(1, [[L["bibliography"], False]], True)
            for b in data["bibliography"]:
                _runs(self.para("Bibliographie"), b)
        self.contents(toc)
        d.core_properties.title = f"{data['title']} — {data['subtitle']}"
        d.core_properties.author = data["account"] or "Marginote"
        d.core_properties.language = LANG.get(data["lang"], "fr-FR")
        out = io.BytesIO()
        d.save(out)
        return out.getvalue()


def docx(doc: dict) -> bytes:
    return _Writer(doc).write()
