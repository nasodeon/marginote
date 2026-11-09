"""PDFs, read with PDFium: the text of each page with the place of every word, the page drawn as a picture
when it is looked at, and the page numbers printed in it.

A PDF page is handled like a page photo: its words have places in 'photo pixels' (the page drawn with its
longer side LONG_SIDE pixels), so choosing a passage on it and highlighting a quote work the same way.
A page with no text (a scan) is read with Tesseract, like a photo.
"""

import io
import logging
import math
import re
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as raw
from PIL import Image

from . import ocr

log = logging.getLogger("marginote")
PDFIUM = threading.Lock()     # PDFium may not be used by two threads at once: every call goes through this
LONG_SIDE = 2000              # a page's longer side, in the pixels its words are placed in
HYPHEN_MARKS = {"￾", "\u0002", "­"}   # how PDFium reports a hyphen that cuts a word at the end of a line
SPACES = {" ", " ", " ", " ", "\t", " ", " "}
BREAKS = {"\r", "\n"}


class NotAPdf(ValueError):
    pass


@dataclass
class PageText:
    index: int                 # 0 for the first page
    width: int                 # in photo pixels
    height: int
    words: list[ocr.Word]
    label: str | None          # the page's own number, as the PDF names it ('45', 'xii'), if it does
    scanned: bool              # no usable text: to be read like a photo


def open_pdf(path: Path) -> pdfium.PdfDocument:
    try:
        return pdfium.PdfDocument(str(path))
    except pdfium.PdfiumError as err:
        raise NotAPdf(str(err)) from None


def count_pages(path: Path) -> tuple[int, dict]:
    """How many pages, and the PDF's own title and author (often empty, sometimes a file name)."""
    with PDFIUM:
        doc = open_pdf(path)
        try:
            meta = doc.get_metadata_dict(skip_empty=True)
            return len(doc), {"title": meta.get("Title"), "author": meta.get("Author")}
        finally:
            doc.close()


def _size(page) -> tuple[int, int, float]:
    w, h = page.get_size()          # as shown, rotation included
    scale = LONG_SIDE / max(w, h, 1)
    return round(w * scale), round(h * scale), scale


def _to_pixels(page, width: int, height: int, box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    """A rectangle in the page's own coordinates (left, bottom, right, top) to photo pixels (x, y, w, h).
    PDFium does the arithmetic, so a cropped or turned page comes out right."""
    xs, ys = [], []
    for px, py in ((box[0], box[1]), (box[2], box[3]), (box[0], box[3]), (box[2], box[1])):
        dx, dy = raw.c_int(), raw.c_int()
        raw.FPDF_PageToDevice(page, 0, 0, width, height, 0, px, py, dx, dy)
        xs.append(dx.value)
        ys.append(dy.value)
    return min(xs), min(ys), max(1, max(xs) - min(xs)), max(1, max(ys) - min(ys))


def _usable(text: str) -> bool:
    """Real text, not a page of a scan with nothing behind it, nor the garbage of a broken font."""
    letters = sum(ch.isalpha() for ch in text)
    return letters >= 20 and letters >= 0.5 * len(text.replace(" ", ""))


LIGATURES = str.maketrans({"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl",
                           "\ufb05": "st", "\ufb06": "st"})
SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def _words(page, width: int, height: int) -> list[ocr.Word]:
    """The page's words in reading order, each with its box and its line. A footnote call or an exponent,
    a small digit above the line, is written raised (lecture¹, 10³); ligatures are spelled out (fi, fl)."""
    textpage = page.get_textpage()
    try:
        out: list[ocr.Word] = []
        chars: list[str] = []
        box: list[float] | None = None      # left, bottom, right, top of the word being read
        line = 0
        base = size = None                   # the line's baseline and font size
        last_right: float | None = None
        gap = False
        sideways = False                     # reading text written up or down a margin

        def finish() -> None:
            nonlocal chars, box
            text = unicodedata.normalize("NFC", "".join(chars).translate(LIGATURES)).strip()
            if text and box:
                x, y, w, h = _to_pixels(page, width, height, tuple(box))
                out.append(ocr.Word(len(out), text, 100.0, x, y, w, h, line))
            chars, box = [], None

        left, right, bottom, top = raw.c_double(), raw.c_double(), raw.c_double(), raw.c_double()
        ox, oy = raw.c_double(), raw.c_double()
        n = textpage.count_chars()
        low = 0
        for i in range(n):
            code = raw.FPDFText_GetUnicode(textpage, i)
            if 0xDC00 <= code < 0xE000 and low:
                continue                     # the second half of a character read just before
            if 0xD800 <= code < 0xDC00 and i + 1 < n:      # a character outside the first 65,536: two halves
                low = raw.FPDFText_GetUnicode(textpage, i + 1)
                code = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00) if 0xDC00 <= low < 0xE000 else code
            else:
                low = 0
            ch = chr(code)
            if 0x1D400 <= code <= 0x1D7FF:
                ch = unicodedata.normalize("NFKC", ch)    # mathematical italic 𝑥 is written x
            if ch in BREAKS or ch in SPACES or (ch.isspace() and ch not in HYPHEN_MARKS):
                gap = True                   # the end of a word, unless an exponent follows close by;
                continue                     # a new line is told by where the next word is
            if not raw.FPDFText_GetCharBox(textpage, i, left, right, bottom, top):
                continue
            raw.FPDFText_GetCharOrigin(textpage, i, ox, oy)
            l, r, b, t, y = left.value, right.value, bottom.value, top.value, oy.value
            turned = abs(math.sin(raw.FPDFText_GetCharAngle(textpage, i))) > 0.5
            if turned or sideways:
                # a line written sideways (an arXiv stamp up the margin): words end at spaces only
                if gap or turned != sideways:
                    finish()
                if turned != sideways:
                    if out and out[-1].line == line:
                        line += 1
                    base = size = last_right = None
                gap, sideways = False, turned
                if turned:
                    chars.append(ch)
                    box = [l, b, r, t] if box is None else [min(box[0], l), min(box[1], b), max(box[2], r), max(box[3], t)]
                    continue
            fs = raw.FPDFText_GetFontSize(textpage, i)
            if fs <= 0.5:
                fs = max(t - b, 1.0) / 0.7
            raised = (size is not None and ch.isdigit() and b > base + 0.25 * size and t - b < 0.6 * size)
            moved = size is not None and not raised and (
                abs(y - base) > 0.6 * max(fs, size)                           # up or down a line
                or (last_right is not None and l < last_right - 3 * size))    # back to the left: a new column
            if gap and not (raised and last_right is not None and l - last_right < 0.3 * size):
                finish()
            gap = False
            if moved:
                finish()
                if out and out[-1].line == line:
                    line += 1
                base = size = last_right = None
            elif chars and not raised and last_right is not None and l - last_right > 0.25 * (size or fs):
                finish()                     # a gap with no space character: two words
            if raised:
                ch = ch.translate(SUPERSCRIPT)
            elif size is None:
                base, size = y, fs
            if ch in HYPHEN_MARKS:
                ch = "-"                     # glued back to the next line's half, as on a photo
            chars.append(ch)
            box = [l, b, r, t] if box is None else [min(box[0], l), min(box[1], b), max(box[2], r), max(box[3], t)]
            last_right = r
        finish()
        return out
    finally:
        textpage.close()


def read_page(doc: pdfium.PdfDocument, index: int) -> PageText:
    """One page's words, with their places. Call with PDFIUM held."""
    page = doc[index]
    try:
        width, height, _ = _size(page)
        words = _words(page, width, height)
        label = doc.get_page_label(index) or None
        scanned = not _usable("".join(w.text for w in words))
        return PageText(index, width, height, [] if scanned else words, label, scanned)
    finally:
        page.close()


def render(path: Path, index: int, width: int, height: int | None = None) -> Image.Image:
    """The page drawn as a picture `width` pixels wide (and exactly `height` high, when given: the words'
    places then fall exactly on it)."""
    with PDFIUM:
        doc = open_pdf(path)
        try:
            page = doc[index]
            try:
                w, _ = page.get_size()
                bitmap = page.render(scale=width / max(w, 1), may_draw_forms=True)
                try:
                    img = bitmap.to_pil().convert("RGB")
                finally:
                    bitmap.close()
                if height and img.size != (width, height):
                    img = img.resize((width, height), Image.Resampling.LANCZOS)
                return img
            finally:
                page.close()
        finally:
            doc.close()


def read_scanned_page(path: Path, index: int, width: int, height: int, langs: str) -> tuple[list[ocr.Word], str | None]:
    """A page with no text: drawn sharp enough for Tesseract, read like a photo, the words placed back
    in photo pixels."""
    big = ocr.MAX_SIDE / max(width, height)
    img = render(path, index, round(width * big), round(height * big))
    reading = ocr.read_page(img, langs, straighten=False)
    shrink = 1 / big
    words = [ocr.Word(w.i, w.text, w.conf, round(w.x * shrink), round(w.y * shrink), max(1, round(w.w * shrink)),
                      max(1, round(w.h * shrink)), w.line) for w in reading.words]
    return words, reading.page


def first_text(path: Path, count: int) -> list[str]:
    """The first pages' text as PDFium reads it on its own, sideways lines included (an arXiv stamp up the
    margin): where a DOI or an arXiv number is looked for."""
    with PDFIUM:
        doc = open_pdf(path)
        try:
            out = []
            for index in range(min(count, len(doc))):
                page = doc[index]
                textpage = page.get_textpage()
                out.append(textpage.get_text_range())
                textpage.close()
                page.close()
            return out
        finally:
            doc.close()


def page_image(path: Path, index: int, width: int, height: int) -> bytes:
    img = render(path, index, width, height)
    out = io.BytesIO()
    img.save(out, format="WEBP", quality=80, method=2)
    return out.getvalue()


_NUMBER = re.compile(r"^\d{1,4}$")


def page_number(label: str | None, words: list[ocr.Word], width: int, height: int) -> str | None:
    """The number printed on the page: the PDF's own page label when it gives one that is not just the
    position in the file, else a lone number at the top or bottom of the page."""
    found = ocr.detect_page(words, width, height)
    if label and (not _NUMBER.match(label) or not found or found == label):
        return label
    return found or label
