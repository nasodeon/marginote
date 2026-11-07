"""Marginote: a small self-hosted app for quotes and notes on what you read, watch and listen to.

Start it with:  uvicorn --factory marginote.main:create_app
Interactive API documentation is served at /docs.
"""

import hashlib
import hmac
import logging
import mimetypes
import time
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

import pytesseract
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from . import backup, db, dewarp, ocr, routes_admin, routes_entries, routes_library, routes_photos
from .config import Settings, load_settings
from .context import Context

VERSION = "0.5.0"
STATIC = Path(__file__).parent / "static"
log = logging.getLogger("marginote")
mimetypes.add_type("application/manifest+json", ".webmanifest")

# The page may load only its own files and talk only to this server: no outside scripts, fonts or trackers.
PAGE_HEADERS = {
    "Cache-Control": "no-cache",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; "
        "font-src 'self'; connect-src 'self'; manifest-src 'self'; object-src 'none'; base-uri 'none'; "
        "frame-ancestors 'none'; form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


class StaticAssets(StaticFiles):
    """The app's own files (script, styles, fonts, icons). Cached a day; a new version gets a new address."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "public, max-age=86400"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


def page_html() -> str:
    """The app page, with its script and styles addressed by a fingerprint of their content."""
    digest = hashlib.sha256()
    for name in ("app.js", "app.css"):
        digest.update((STATIC / name).read_bytes())
    return (STATIC / "index.html").read_text(encoding="utf-8").replace("{{version}}", digest.hexdigest()[:12])


class LoginIn(BaseModel):
    password: str


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    ctx = Context(settings)
    ctx.files.make_folders()
    # an existing database is copied to backups/ before its shape changes: the way back to the old version
    db.migrate(settings.db_path, before_upgrade=lambda old: backup.before_upgrade(
        settings.db_path, settings.backups_dir, VERSION))

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        logging.basicConfig(level=logging.INFO)
        if not settings.password:
            log.warning("MARGINOTE_PASSWORD is empty: nobody can log in until you set it in the compose file")
        backup.start_maintenance(settings.db_path, settings.backups_dir, settings.backup_hour, settings.backups_kept,
                                 settings.backups_monthly, hourly=ctx.files.clean_unused_photos)
        routes_photos.start_reader(ctx)
        yield
        ctx.reader_queue.put(None)

    # The session cookie holds this tag, derived from the password: changing the password logs every device out.
    login_tag = (
        hmac.new(settings.secret_key().encode(), settings.password.encode(), hashlib.sha256).hexdigest()[:32]
        if settings.password else ""
    )

    def logged_in(request: Request) -> bool:
        return bool(login_tag) and hmac.compare_digest(str(request.session.get("ok", "")), login_tag)

    def require_login(request: Request) -> None:
        if not logged_in(request):
            raise HTTPException(401, "Log in first with POST /api/login")

    ctx.auth = [Depends(require_login)]

    app = FastAPI(
        title="Marginote",
        version=VERSION,
        description=(
            "Quotes and notes on what you read, watch and listen to, self-hosted.\n\n"
            "**To test here:** open `POST /api/login`, click *Try it out*, type your password, "
            "then *Execute*. Every other call works after that."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key(),
        session_cookie="marginote_session",
        max_age=180 * 24 * 3600,
        same_site="lax",
        https_only=settings.cookie_secure,
    )

    ctx.files.refile_photos()
    ctx.files.clean_unused_photos()

    @lru_cache(maxsize=1)
    def tesseract_info() -> tuple[str | None, frozenset]:
        try:
            return str(pytesseract.get_tesseract_version()), frozenset(pytesseract.get_languages(config=""))
        except Exception:  # Tesseract missing
            return None, frozenset()

    @app.get("/api/health", tags=["status"])
    def health():
        """Is the app running? No login needed."""
        tesseract, installed = tesseract_info()
        wanted = settings.ocr_langs.split("+")
        return {
            "status": "ok",
            "version": VERSION,
            "tesseract": tesseract,
            "ocr_languages": [lang for lang in wanted if lang in installed],
            "missing_ocr_languages": [lang for lang in wanted if lang not in installed],
            "straighten_pages": settings.straighten_pages and dewarp.available(),
            "barcode_reader": ocr.BARCODE_READER,
            "lookups_enabled": settings.lookups_enabled,
            "password_set": bool(settings.password),
        }

    @app.post("/api/login", tags=["status"])
    def login(body: LoginIn, request: Request):
        if not settings.password:
            raise HTTPException(503, "Set MARGINOTE_PASSWORD in the compose file, then redeploy the app")
        if not hmac.compare_digest(body.password.encode(), settings.password.encode()):
            time.sleep(1)
            raise HTTPException(401, "Wrong password")
        request.session["ok"] = login_tag
        return {"logged_in": True}

    @app.post("/api/logout", tags=["status"])
    def logout(request: Request):
        request.session.clear()
        return {"logged_in": False}

    @app.get("/api/me", tags=["status"])
    def me(request: Request):
        return {"logged_in": logged_in(request)}

    for module in (routes_library, routes_entries, routes_photos, routes_admin):
        app.include_router(module.router(ctx))

    app.mount("/static", StaticAssets(directory=STATIC), name="static")
    page = page_html()

    @app.get("/", include_in_schema=False)
    def app_page():
        return HTMLResponse(page, headers=PAGE_HEADERS)

    return app
