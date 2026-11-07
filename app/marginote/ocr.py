"""Photo handling and text recognition (Tesseract), page-number detection and passage selection."""

import ctypes
import importlib.util
import io
import os
import re
from dataclasses import asdict, dataclass

# One thread is the fastest for a single page (measured), and leaves the other cores free.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")

import pytesseract
from PIL import Image, ImageFilter, ImageMath, ImageOps, UnidentifiedImageError

from . import dewarp
from .lookup import clean_isbn, isbn13

# The barcode reader and the HEIC decoder are loaded the first time they are needed, not at start:
# most of the time the app waits, and they would hold memory for nothing.
BARCODE_READER = importlib.util.find_spec("zxingcpp") is not None


_trim = None


def release_memory() -> None:
    """Give the memory used to read a page back to the system now (otherwise it stays held for later)."""
    global _trim
    if _trim is None:
        try:
            _trim = ctypes.CDLL("libc.so.6").malloc_trim
        except (OSError, AttributeError):  # not glibc
            _trim = False
    if _trim:
        _trim(0)


def _open_heic_too() -> bool:
    try:  # iPhone photos sent as they are (not shrunk by the app) are often HEIC
        from pillow_heif import register_heif_opener
    except ImportError:  # pragma: no cover
        return False
    register_heif_opener()
    return True

MAX_SIDE = 2400  # long edge after resizing: sharp enough for OCR, ~0.5 MB as JPEG


@dataclass
class Word:
    i: int        # position in reading order
    text: str
    conf: float
    x: int
    y: int
    w: int
    h: int
    line: int     # running line number, shared by words on the same line


def open_image(data: bytes) -> Image.Image:
    try:
        return Image.open(io.BytesIO(data))
    except UnidentifiedImageError:
        if not _open_heic_too():
            raise
        return Image.open(io.BytesIO(data))


def normalize_photo(data: bytes) -> Image.Image:
    """Open any phone photo, apply its rotation and shrink it (long edge 2400 px)."""
    img = open_image(data)
    if img.format == "JPEG":
        # decode big photos at half or quarter size directly: less memory, faster
        scale = MAX_SIDE / max(img.size)
        if scale < 1:
            img.draft("RGB", (int(img.size[0] * scale), int(img.size[1] * scale)))
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    return img


PHOTO_SUFFIX = ".webp"


def to_stored(img: Image.Image) -> bytes:
    """The copy that is kept: WebP, no metadata (no location, camera or date).

    Measured on page photos: about half the size of a JPEG of the same quality (200-340 KB instead of
    480-660 KB), for about 0.2 s more work.
    """
    out = io.BytesIO()
    img.save(out, format="WEBP", quality=80, method=2)
    return out.getvalue()


COVER_SUFFIX = ".webp"


def normalize_cover(data: bytes, max_side: int = 600) -> bytes:
    """A cover or a video thumbnail as kept: at most 600 px, WebP, no metadata (about 30 KB)."""
    img = open_image(data)
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((max_side, max_side))
    out = io.BytesIO()
    img.save(out, format="WEBP", quality=80, method=4)
    return out.getvalue()


def even_lighting(gray: Image.Image) -> Image.Image:
    """Remove shadows (the spine of an open book, a hand, uneven light) before reading.

    Estimates the paper's brightness everywhere, with the text filtered out, then divides it out.
    Measured on shadowed test pages: 83-88% of words read before, about 97% after; no change on
    evenly lit pages; about 60 ms of extra work.
    """
    w, h = gray.size
    small = gray.resize((max(1, w // 8), max(1, h // 8)), Image.Resampling.BOX)
    paper = small.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(2))
    paper = paper.resize((w, h), Image.Resampling.BILINEAR)
    # Worked out in bands of 256 rows: the arithmetic needs several full-size copies in floating point
    # (4 bytes a pixel), about 100 MB for a whole page at once, under 10 MB a band. Same result.
    out = Image.new("L", (w, h))
    for top in range(0, h, 256):
        box = (0, top, w, min(h, top + 256))
        out.paste(ImageMath.lambda_eval(
            lambda m: m["convert"](m["min"](m["float"](m["g"]) * 255 / (m["float"](m["p"]) + 1), 255), "L"),
            g=gray.crop(box), p=paper.crop(box),
        ), box)
    return out


@dataclass
class PageReading:
    words: list[Word]
    page: str | None       # printed page number, if found
    photo: Image.Image     # the photo to keep; word positions refer to it
    straightened: bool     # True when the photo was straightened before reading


def read_page(img: Image.Image, langs: str, straighten: bool = True) -> PageReading:
    """Read a photographed page: even out shadows, straighten curved lines, read the words,
    find the page number."""
    gray = even_lighting(ImageOps.grayscale(img))
    photo, straightened = img, False
    if straighten:
        flat = dewarp.straighten(gray, img)
        if flat is not None:
            gray, photo = flat
            straightened = True
    gray = ImageOps.autocontrast(gray, cutoff=1)
    words = _read_words(gray, langs)
    page = detect_page(words, gray.width, gray.height)
    if page is None:
        try:
            page = find_page_number(gray, words, langs)
        except pytesseract.TesseractError:  # a missing page number must never lose the page
            page = None
    return PageReading(words, page, photo, straightened)


def recognize(img: Image.Image, langs: str) -> list[Word]:
    """Run Tesseract on a photo as it is (no straightening) and return its words in reading order."""
    return _read_words(ImageOps.autocontrast(even_lighting(ImageOps.grayscale(img)), cutoff=1), langs)


def _read_words(gray: Image.Image, langs: str) -> list[Word]:
    """Run Tesseract and keep every recognized word with its box, in reading order."""
    data = pytesseract.image_to_data(
        gray, lang=langs, config="--oem 1 --psm 3", output_type=pytesseract.Output.DICT
    )
    words: list[Word] = []
    line_ids: dict[tuple[int, int, int], int] = {}
    for k, raw in enumerate(data["text"]):
        text = (raw or "").strip()
        try:
            conf = float(data["conf"][k])
        except (TypeError, ValueError):
            conf = -1.0
        if not text or conf < 0:
            continue
        key = (data["block_num"][k], data["par_num"][k], data["line_num"][k])
        line = line_ids.setdefault(key, len(line_ids))
        words.append(Word(
            i=len(words), text=text, conf=conf,
            x=int(data["left"][k]), y=int(data["top"][k]),
            w=int(data["width"][k]), h=int(data["height"][k]), line=line,
        ))
    return words


def words_to_dicts(words: list[Word]) -> list[dict]:
    return [asdict(w) for w in words]


def words_for_browser(words: list[Word]) -> list[dict]:
    """What the selection screen needs (no confidence): position, text and line of each word."""
    return [{"i": w.i, "text": w.text, "x": w.x, "y": w.y, "w": w.w, "h": w.h, "line": w.line} for w in words]


def words_from_dicts(items: list[dict]) -> list[Word]:
    return [Word(**item) for item in items]


# ---------- page number ----------

_PAGE_TOKEN = re.compile(r"^[\(\[\-–—•·]*(\d{1,4}|[ivxlcdm]{1,7})[\)\]\-–—•·.]*$", re.I)
_ROMAN = re.compile(r"^(?=[mdclxvi])m{0,4}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$", re.I)


def detect_page(words: list[Word], width: int, height: int) -> str | None:
    """Find the printed page number: a lone number in the top or bottom strip of the page."""
    if not words or height <= 0:
        return None
    band = 0.14 * height
    per_line: dict[int, int] = {}
    for w in words:
        per_line[w.line] = per_line.get(w.line, 0) + 1

    best: tuple[float, str] | None = None
    for w in words:
        top_dist = w.y
        bottom_dist = height - (w.y + w.h)
        edge_dist = min(top_dist, bottom_dist)
        if edge_dist > band:
            continue
        m = _PAGE_TOKEN.match(w.text)
        if not m:
            continue
        token = m.group(1)
        is_digit = token.isdigit()
        if not is_digit and (not _ROMAN.match(token) or per_line[w.line] > 2):
            continue
        if is_digit and int(token) == 0:
            continue
        score = (
            w.conf / 100
            + (0.6 if is_digit else 0.0)
            + 0.5 * (1 - edge_dist / band)
            + (0.4 if per_line[w.line] <= 3 else 0.0)
            - (0.5 if is_digit and len(token) == 4 else 0.0)  # more likely a year than a page
        )
        if best is None or score > best[0]:
            best = (score, token.lower())
    return best[1] if best else None


def _text_block(words: list[Word]) -> tuple[int, int, int, int, int] | None:
    """Where the main text sits (top, bottom, left, right) and its usual word height,
    from lines with at least three well-read words."""
    lines: dict[int, list[Word]] = {}
    for w in words:
        if w.conf >= 60 and sum(c.isalpha() for c in w.text) >= 3:
            lines.setdefault(w.line, []).append(w)
    body = [w for ws in lines.values() if len(ws) >= 3 for w in ws]
    if len(body) < 9:
        return None
    heights = sorted(w.h for w in body)
    return (min(w.y for w in body), max(w.y + w.h for w in body),
            min(w.x for w in body), max(w.x + w.w for w in body), max(8, heights[len(heights) // 2]))


def _ink_marks(ink: Image.Image, scale: int) -> list[tuple[int, int, int, int]]:
    """Boxes around each separate patch of ink (pixels that touch), found on a reduced copy."""
    small = ink.reduce(scale) if scale > 1 else ink
    w, h = small.size
    px = small.tobytes()
    seen = bytearray(w * h)
    marks = []
    for start in range(w * h):
        if seen[start] or px[start] < 64:
            continue
        seen[start] = 1
        stack = [start]
        x0 = x1 = start % w
        y0 = y1 = start // w
        while stack:
            p = stack.pop()
            x, y = p % w, p // w
            x0, x1, y0, y1 = min(x0, x), max(x1, x), min(y0, y), max(y1, y)
            for ny in (y - 1, y, y + 1):
                if 0 <= ny < h:
                    for nx in (x - 1, x, x + 1):
                        q = ny * w + nx
                        if 0 <= nx < w and not seen[q] and px[q] >= 64:
                            seen[q] = 1
                            stack.append(q)
        marks.append((x0 * scale, y0 * scale, (x1 + 1) * scale, (y1 + 1) * scale))
    return marks


def _group_marks(marks: list[tuple[int, int, int, int]], gap: int) -> list[tuple[int, int, int, int]]:
    """Join marks side by side on the same line (the digits of one number, the parts of a letter)."""
    groups: list[list[int]] = []
    for x0, y0, x1, y1 in sorted(marks):
        for g in groups:
            overlap = min(y1, g[3]) - max(y0, g[1])
            if x0 - g[2] <= gap and overlap > 0.5 * min(y1 - y0, g[3] - g[1]):
                g[0], g[1], g[2], g[3] = min(g[0], x0), min(g[1], y0), max(g[2], x1), max(g[3], y1)
                break
        else:
            groups.append([x0, y0, x1, y1])
    return [(a, b, c, d) for a, b, c, d in groups]


def find_page_number(gray: Image.Image, words: list[Word], langs: str) -> str | None:
    """Second look for a page number the main reading skipped (Tesseract often drops a lone digit).

    Looks just below and just above the text, keeps only marks the size of a number (not the
    table, a thumb or the next page), and reads each alone, digits and roman numerals only.
    About 0.1 s per mark read.
    """
    block = _text_block(words)
    if block is None:
        return None
    top, bottom, left, right, lh = block
    width, height = gray.size
    x0, x1 = max(0, left - lh), min(width, right + lh)
    found: list[tuple[float, str]] = []
    for y0, y1 in ((bottom + lh // 2, bottom + 6 * lh), (top - 6 * lh, top - lh // 2)):
        y0, y1 = max(0, y0), min(height, y1)
        if y1 - y0 < lh:
            continue
        band = gray.crop((x0, y0, x1, y1))
        ink = band.point(lambda v: 255 if v < 128 else 0).filter(ImageFilter.MedianFilter(3))
        marks = [
            m for m in _ink_marks(ink, max(1, lh // 10))
            if m[2] - m[0] < 2 * lh and m[3] - m[1] < 2 * lh   # the table, a thumb, the next page: too big
            and m[0] > 0 and m[2] < ink.width                  # cut by the side: part of something bigger
        ]
        groups = _group_marks(marks, gap=lh // 2)
        candidates = [
            g for g in groups
            if 0.45 * lh <= g[3] - g[1] <= 1.6 * lh and 0.2 * lh <= g[2] - g[0] <= 5 * lh
            and not any(  # alone on its line, unlike the number starting a footnote
                o is not g and min(g[3], o[3]) > max(g[1], o[1])
                and max(o[0] - g[2], g[0] - o[2]) < 1.5 * lh
                for o in groups
            )
        ]
        # nearest to the text first; a page number sits close to it
        candidates.sort(key=lambda g: g[1] if y0 > top else -g[3])
        for gx0, gy0, gx1, gy1 in candidates[:3]:
            piece = ImageOps.expand(band.crop((gx0, gy0, gx1, gy1)), border=lh, fill=255)
            data = pytesseract.image_to_data(
                piece, lang=langs,
                config="--oem 1 --psm 7 -c tessedit_char_whitelist=0123456789ivxlcdmIVXLCDM",
                output_type=pytesseract.Output.DICT,
            )
            for raw, conf in zip(data["text"], data["conf"]):
                token = (raw or "").strip()
                try:
                    conf = float(conf)
                except (TypeError, ValueError):
                    continue
                if token.isdigit() and len(token) <= 4 and int(token) > 0 and conf >= 50:
                    found.append((conf - (30 if len(token) == 4 else 0), token))
                elif _ROMAN.match(token) and len(token) <= 7 and conf >= 75:
                    found.append((conf - 10, token.lower()))
    return max(found)[1] if found else None


# ---------- ISBN from a photo of the back cover ----------

_ISBN_AFTER_LABEL = re.compile(r"ISBN(?:-?1[03])?[\s:]*([0-9Xx][0-9Xx\s\u2010-\u2013-]{8,20})", re.I)
_EAN_LIKE = re.compile(r"97[89][\d\s\u2010-\u2013-]{10,16}")


def isbns_in_text(text: str) -> list[str]:
    """Valid ISBNs written in a text ('ISBN 978-2-07-036002-4', 'ISBN 2-07-036002-4', a bare 978… number),
    as ISBN-13, in the order found."""
    found: list[str] = []
    for raw in [m.group(1) for m in _ISBN_AFTER_LABEL.finditer(text)] + [m.group(0) for m in _EAN_LIKE.finditer(text)]:
        digits = re.sub(r"[^0-9Xx]", "", raw).upper()
        for size in (13, 10):
            code = clean_isbn(digits[:size]) if len(digits) >= size else None
            if code:
                code = isbn13(code)
                if code not in found:
                    found.append(code)
                break
    return found


def find_isbn(img: Image.Image, langs: str) -> tuple[str | None, str]:
    """The ISBN on a photo of a back cover: from the barcode if it can be read, else from the printed number.

    Returns (ISBN-13 or None, "barcode" | "text" | "").
    """
    if BARCODE_READER:
        import zxingcpp
        for result in zxingcpp.read_barcodes(img, formats=zxingcpp.BarcodeFormat.EAN13):
            code = clean_isbn(result.text)
            if code and code.startswith(("978", "979")):
                return code, "barcode"
    # no clipping here (cutoff=0): a back cover is mostly empty, and clipping the darkest 1% of pixels would
    # erase its few lines of text
    gray = ImageOps.autocontrast(even_lighting(ImageOps.grayscale(img)), cutoff=0)
    text = pytesseract.image_to_string(gray, lang=langs, config="--oem 1 --psm 11")
    found = isbns_in_text(text)
    return (found[0], "text") if found else (None, "")


# ---------- passage selection ----------

_HYPHENS = ("-", "‐", "‑", "¬")


def join_words(words: list[Word]) -> str:
    """Join words into a passage; words cut with a hyphen at the end of a line are glued back."""
    parts: list[str] = []
    for idx, w in enumerate(words):
        if not parts:
            parts.append(w.text)
            continue
        prev = words[idx - 1]
        if prev.line != w.line and prev.text.endswith(_HYPHENS) and len(prev.text) > 1:
            parts[-1] = parts[-1][:-1] + w.text
        else:
            parts.append(" " + w.text)
    text = "".join(parts)
    # tidy spaces Tesseract may leave inside quotes and before closing punctuation
    text = re.sub(r"\s+([,.)\]…”])", r"\1", text)
    text = re.sub(r"([“(\[])\s+", r"\1", text)
    return text.strip()


def select_range(words: list[Word], start: int, end: int) -> str:
    if start > end:
        start, end = end, start
    chosen = [w for w in words if start <= w.i <= end]
    return join_words(chosen)


def select_box(words: list[Word], x: int, y: int, w: int, h: int) -> tuple[str, int | None, int | None]:
    """Fallback selection: every word whose centre falls inside the rectangle."""
    inside = [
        word for word in words
        if x <= word.x + word.w / 2 <= x + w and y <= word.y + word.h / 2 <= y + h
    ]
    if not inside:
        return "", None, None
    return join_words(inside), inside[0].i, inside[-1].i


def full_text(words: list[Word]) -> str:
    lines: dict[int, list[Word]] = {}
    for w in words:
        lines.setdefault(w.line, []).append(w)
    return "\n".join(join_words(ws) for _, ws in sorted(lines.items()))
