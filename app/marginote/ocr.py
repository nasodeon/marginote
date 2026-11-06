"""Photo handling and text recognition (Tesseract), page-number detection and passage selection."""

import io
import re
from dataclasses import asdict, dataclass

import pytesseract
from PIL import Image, ImageOps

try:  # iPhone photos are often HEIC
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover
    pass

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


def normalize_photo(data: bytes) -> tuple[Image.Image, bytes]:
    """Open any phone photo, apply its rotation, shrink it, and return it plus a JPEG copy to store."""
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85, optimize=True)
    return img, out.getvalue()


def normalize_cover(data: bytes, max_side: int = 600) -> bytes:
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((max_side, max_side))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85, optimize=True)
    return out.getvalue()


def recognize(img: Image.Image, langs: str) -> list[Word]:
    """Run Tesseract and keep every recognized word with its box, in reading order."""
    gray = ImageOps.autocontrast(ImageOps.grayscale(img), cutoff=1)
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
        )
        if best is None or score > best[0]:
            best = (score, token.lower())
    return best[1] if best else None


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
