import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

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
