import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

import dataclasses

from marginote.config import Settings
from marginote.main import create_app

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
]

PAGE_LINES = [
    "On fait la science avec des faits comme on fait une",
    "maison avec des pierres ; mais une accumulation de",
    "faits n’est pas plus une science qu’un tas de pier-",
    "res n’est une maison. Douter de tout ou tout croire,",
    "ce sont deux solutions également commodes.",
]


def _font(size: int):
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def make_page(page_number: str = "168", fmt: str = "JPEG") -> bytes:
    """A fake photo of a book page: running head, five lines of text, page number at the bottom."""
    img = Image.new("RGB", (1240, 1700), (250, 247, 240))
    draw = ImageDraw.Draw(img)
    draw.text((330, 90), "LES HYPOTHÈSES EN PHYSIQUE", font=_font(30), fill=(90, 80, 70))
    body = _font(40)
    y = 260
    for line in PAGE_LINES:
        draw.text((110, y), line, font=body, fill=(30, 28, 25))
        y += 72
    draw.text((595, 1560), page_number, font=_font(36), fill=(30, 28, 25))
    out = io.BytesIO()
    img.save(out, format=fmt, quality=92)
    return out.getvalue()


LONG_TEXT = (
    "La lecture lente laisse au lecteur le temps de noter ce qui le frappe dans la marge "
    "du livre, puis de revenir plus tard sur ces traces pour retrouver une idée, une image "
    "ou une question restée ouverte depuis la première lecture du chapitre entier."
).split()


def make_full_page(page_number: str = "6", lines: int = 22) -> tuple[Image.Image, list[str]]:
    """A page filled with text (enough lines to model a curve), page number just below the text.

    Returns the image and the words written on it, in order.
    """
    img = Image.new("RGB", (1240, 1700), (250, 247, 240))
    draw, font = ImageDraw.Draw(img), _font(34)
    words, k, y, written = LONG_TEXT * 10, 0, 140, []
    for _ in range(lines):
        line: list[str] = []
        while k < len(words) and draw.textlength(" ".join(line + [words[k]]), font=font) < 1020:
            line.append(words[k])
            k += 1
        draw.text((110, y), " ".join(line), font=font, fill=(30, 28, 25))
        written += line
        y += 54
    if page_number:
        draw.text((610, y + 34), page_number, font=font, fill=(30, 28, 25))
    return img, written


def bend_toward_spine(img: Image.Image, strength: float = 0.14, reach: float = 0.45) -> Image.Image:
    """Curve the lines near the left edge, like a page rising toward the spine of an open book."""
    width, height = img.size
    out = Image.new("RGB", img.size, (250, 247, 240))
    step = 4
    for x in range(0, width, step):
        t = max(0.0, 1 - x / (reach * width))
        stretch = 1 + strength * t * t
        column = img.crop((x, 0, x + step, height)).resize((step, int(height * stretch)))
        out.paste(column, (x, int((height - height * stretch) / 2)))
    return out


def as_jpeg(img: Image.Image) -> bytes:
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
    return out.getvalue()


def word_recall(got: list[str], written: list[str]) -> float:
    """Share of the written words found, in order (punctuation ignored)."""
    import difflib

    clean = [w.strip(".,;:") for w in got]
    want = [w.strip(".,;:") for w in written]
    matcher = difflib.SequenceMatcher(None, want, clean, autojunk=False)
    return sum(b.size for b in matcher.get_matching_blocks()) / len(want)


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        password="correct horse",
        ocr_langs="fra+eng",
        lookups_enabled=True,
        cookie_secure=False,
        backup_hour=3,
        backups_kept=14,
    )


@pytest.fixture()
def client(settings: Settings):
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture()
def logged_in(client: TestClient) -> TestClient:
    r = client.post("/api/login", json={"password": "correct horse"})
    assert r.status_code == 200
    return client


def owner(settings: Settings) -> Settings:
    """The owner's library folder (data/users/owner/), with the same names for its files."""
    return dataclasses.replace(settings, data_dir=settings.data_dir / "users" / "owner")
