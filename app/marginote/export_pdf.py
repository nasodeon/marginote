"""The PDF of an export, typeset by Typst (a typesetting program, like LaTeX but small and fast, inside Python).
Computer Modern, the app's typeface, is built into it: no font file to add. The document comes in as data."""

import functools
import json
from pathlib import Path

TEMPLATE = Path(__file__).parent / "templates" / "export.typ"

try:
    import typst
    AVAILABLE = True
except ImportError:          # pragma: no cover - the image always has it
    typst = None
    AVAILABLE = False


def pdf(doc: dict) -> bytes:
    if typst is None:
        raise RuntimeError("Typst is not installed")
    return typst.compile(str(TEMPLATE), sys_inputs={"data": json.dumps(doc, ensure_ascii=False)})


@functools.cache
def works() -> bool:
    """Can this server make a PDF? Checked once, with a one-quote document (for /api/health)."""
    if typst is None:
        return False
    sample = {"lang": "fr", "title": "Test", "subtitle": "Test", "byline": "", "account": "", "short": "", "date": "",
              "labels": {"contents": "Sommaire", "bibliography": "Bibliographie", "note": "Note", "comment": "Commentaire",
                         "open": "«\u202f", "close": "\u202f»"},
              "chapters": [{"title": [["Test", False]], "meta": "", "sections": [{"label": "", "outlined": False, "groups": [
                  {"sid": None, "head": None, "level": 2, "items": [
                      {"type": "quote", "id": 1, "text": "Test", "ref": [["Test", True]], "topics": [], "comment": ""}]}]}]}],
              "bibliography": [], "counts": {}}
    try:
        return pdf(sample).startswith(b"%PDF")
    except Exception:
        return False
