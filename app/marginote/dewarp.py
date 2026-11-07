"""Straighten the curved lines of a photographed book page, using Leptonica.

Leptonica is the image library Tesseract is built on, so it is already installed with it; it is
called directly (ctypes) because no Python package wraps its page-straightening functions.

Measured on real phone photos of an open paperback: words read on a page curving toward the
spine went from 46% to 90% and from 74% to 97%; a flat page was unchanged; about 0.4 s per page.
If Leptonica cannot be found, or finds too few text lines to model the curve, the page is read
as it was.
"""

import ctypes
import ctypes.util
import io
import logging

from PIL import Image

log = logging.getLogger("marginote")

_P = ctypes.c_void_p
_IFF_PNM = 11          # Leptonica's code for the PNM format, used to pass images in and out
_SEVERITY_NONE = 6     # no Leptonica messages on stderr

# How curved a page may be before Leptonica refuses to model it. Its defaults are meant for
# flat-bed scans and reject the strong curve near the spine of a photographed paperback.
# Order: max line curvature, min and max difference between top and bottom lines,
# max left and right edge curvature, max edge slope (Leptonica units).
_CURVATURE_LIMITS = (400, 0, 400, 200, 200, 300)


def _load():
    names = [ctypes.util.find_library(n) for n in ("leptonica", "lept")]
    names += ["libleptonica.so.6", "liblept.so.5"]
    for name in names:
        if not name:
            continue
        try:
            lib = ctypes.CDLL(name)
            lib.dewarpSinglePageInit  # noqa: B018 (older versions lack it: skip them)
        except (OSError, AttributeError):
            continue
        return lib
    return None


def _setup(lib):
    lib.setMsgSeverity.argtypes = [ctypes.c_int]
    lib.setMsgSeverity.restype = ctypes.c_int
    lib.pixReadMem.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
    lib.pixReadMem.restype = _P
    lib.pixWriteMem.argtypes = [ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte)),
                                ctypes.POINTER(ctypes.c_size_t), _P, ctypes.c_int]
    lib.pixWriteMem.restype = ctypes.c_int
    lib.pixDestroy.argtypes = [ctypes.POINTER(_P)]
    lib.pixDestroy.restype = None
    lib.lept_free.argtypes = [_P]
    lib.lept_free.restype = None
    lib.dewarpSinglePageInit.argtypes = [_P, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                         ctypes.POINTER(_P), ctypes.POINTER(_P)]
    lib.dewarpSinglePageInit.restype = ctypes.c_int
    lib.dewarpaSetCurvatures.argtypes = [_P] + [ctypes.c_int] * 6
    lib.dewarpaSetCurvatures.restype = ctypes.c_int
    lib.dewarpSinglePageRun.argtypes = [_P, _P, _P, ctypes.POINTER(_P), ctypes.c_int]
    lib.dewarpSinglePageRun.restype = ctypes.c_int
    lib.dewarpaApplyDisparity.argtypes = [_P, ctypes.c_int, _P, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                          ctypes.POINTER(_P), ctypes.c_char_p]
    lib.dewarpaApplyDisparity.restype = ctypes.c_int
    lib.dewarpaDestroy.argtypes = [ctypes.POINTER(_P)]
    lib.dewarpaDestroy.restype = None
    lib.setMsgSeverity(_SEVERITY_NONE)
    return lib


try:
    _lib = _load()
    if _lib is not None:
        _setup(_lib)
except Exception:  # pragma: no cover - a broken library must never stop the app
    log.exception("Leptonica found but unusable; pages will not be straightened")
    _lib = None


def available() -> bool:
    return _lib is not None


def _to_pix(img: Image.Image) -> _P:
    buf = io.BytesIO()
    img.save(buf, format="PPM")  # PGM for a grey image, PPM for colour
    data = buf.getvalue()
    return _P(_lib.pixReadMem(data, len(data)))


def _from_pix(pix: _P, mode: str) -> Image.Image | None:
    out = ctypes.POINTER(ctypes.c_ubyte)()
    size = ctypes.c_size_t()
    if _lib.pixWriteMem(ctypes.byref(out), ctypes.byref(size), pix, _IFF_PNM) != 0 or not out:
        return None
    try:
        img = Image.open(io.BytesIO(ctypes.string_at(out, size.value)))
        img.load()
    finally:
        _lib.lept_free(ctypes.cast(out, _P))
    return img.convert(mode)


def straighten(gray: Image.Image, color: Image.Image) -> tuple[Image.Image, Image.Image] | None:
    """Straighten a page. Returns (grey, colour) bent the same way, or None to keep the photo as is.

    The curve is modelled once, from the grey image with shadows already evened out, then applied
    to both: the grey copy is read, the colour copy is kept, and word positions match both.
    """
    if _lib is None:
        return None
    pixs, pixb, pixd, pixc, pixcd, dewa = _P(), _P(), _P(), _P(), _P(), _P()
    try:
        pixs = _to_pix(gray)
        if not pixs:
            return None
        # threshold 0 = default, adaptive binarization, model vertical and horizontal bending, no column check
        if _lib.dewarpSinglePageInit(pixs, 0, 1, 1, 0, ctypes.byref(pixb), ctypes.byref(dewa)) != 0 or not dewa:
            return None
        _lib.dewarpaSetCurvatures(dewa, *_CURVATURE_LIMITS)
        if _lib.dewarpSinglePageRun(pixs, pixb, dewa, ctypes.byref(pixd), 0) != 0 or not pixd:
            return None
        pixc = _to_pix(color)
        # page 0, fill uncovered edges from the nearest pixels, no offset, no debug file
        if not pixc or _lib.dewarpaApplyDisparity(dewa, 0, pixc, -1, 0, 0, ctypes.byref(pixcd), None) != 0 \
                or not pixcd:
            return None
        flat_gray = _from_pix(pixd, "L")
        flat_color = _from_pix(pixcd, "RGB")
        if flat_gray is None or flat_color is None or flat_gray.size != gray.size \
                or flat_color.size != color.size:
            return None
        return flat_gray, flat_color
    except Exception:
        log.exception("Straightening failed; reading the page as photographed")
        return None
    finally:
        for pix in (pixs, pixb, pixd, pixc, pixcd):
            if pix:
                _lib.pixDestroy(ctypes.byref(pix))
        if dewa:
            _lib.dewarpaDestroy(ctypes.byref(dewa))
