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
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from . import backup, dewarp, ocr, routes_admin, routes_entries, routes_library, routes_photos
from .accounts import LANGUAGES, OWNER, check_password, public
from .config import Settings, load_settings
from .context import Context

VERSION = "0.7.1"
# the release that gave the database its current shape: names the copy made before upgrading to it
SHAPE_CHANGED_IN = "0.6.0"
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


SCRIPTS = {"en": "app.js", "fr": "app.fr.js"}     # the same screens, in English or in French
LANG_COOKIE = "marginote_lang"                      # the language of the login page, before anyone logs in


def page_html(lang: str) -> str:
    """The app page in one language, with its script and styles addressed by a fingerprint of their content."""
    digest = hashlib.sha256()
    for name in (SCRIPTS[lang], "app.css"):
        digest.update((STATIC / name).read_bytes())
    return ((STATIC / "index.html").read_text(encoding="utf-8")
            .replace("{{version}}", digest.hexdigest()[:12]).replace("{{script}}", SCRIPTS[lang])
            .replace("{{lang}}", lang))


class LoginIn(BaseModel):
    name: str = Field("", description="Your name; left empty, the owner (whose password is MARGINOTE_PASSWORD)")
    password: str


class PasswordChange(BaseModel):
    current: str
    new: str


class MePatch(BaseModel):
    name: str | None = None
    language: str | None = Field(None, description="fr or en")
    password: PasswordChange | None = None


class AccountIn(BaseModel):
    name: str
    password: str
    language: str = "fr"


class AccountPatch(BaseModel):
    password: str = Field(description="A new password for this person")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    logging.basicConfig(level=logging.INFO)    # before the libraries open: what they do appears in the log
    ctx = Context(settings, SHAPE_CHANGED_IN, VERSION)
    ctx.libraries()     # every library is opened, and brought up to date, now rather than at first use

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if not settings.password:
            log.warning("MARGINOTE_PASSWORD is empty: the owner cannot log in until you set it in the compose file")
        backup.start_maintenance(ctx.libraries, settings.backup_hour, settings.backups_kept, settings.backups_monthly)
        routes_photos.start_reader(ctx)
        yield
        ctx.reader_queue.put(None)

    def require_owner(request: Request) -> dict:
        account = ctx.account_for(request)
        if account is None:
            raise HTTPException(401, "Log in first with POST /api/login")
        if account["id"] != OWNER:
            raise HTTPException(403, "Only the owner manages accounts")
        return account

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

    # ----- logging in, and your own account -----

    @app.post("/api/login", tags=["account"])
    def login(body: LoginIn, request: Request):
        account = ctx.accounts.by_name(body.name) if body.name.strip() else ctx.accounts.get(OWNER)
        if account and account["id"] == OWNER:
            if not settings.password:
                raise HTTPException(503, "Set MARGINOTE_PASSWORD in the compose file, then redeploy the app")
            ok = hmac.compare_digest(body.password.encode(), settings.password.encode())
        else:
            ok = bool(account) and check_password(body.password, account.get("password"))
        if not ok:
            time.sleep(1)
            raise HTTPException(401, "Wrong name or password")
        request.session.clear()
        request.session.update(uid=account["id"], tag=ctx.session_tag(account))
        return {"logged_in": True, **public(account)}

    @app.post("/api/logout", tags=["account"])
    def logout(request: Request):
        request.session.clear()
        return {"logged_in": False}

    @app.get("/api/me", tags=["account"])
    def me(request: Request):
        """Who is logged in (no login needed to ask)."""
        account = ctx.account_for(request)
        return {"logged_in": True, **public(account)} if account else {"logged_in": False}

    @app.patch("/api/me", tags=["account"])
    def update_me(body: MePatch, request: Request):
        """Your name, your language, your password (the owner's is in the compose file)."""
        account = ctx.account_for(request)
        if account is None:
            raise HTTPException(401, "Log in first with POST /api/login")
        if body.language is not None and body.language not in LANGUAGES:
            raise HTTPException(422, "The language is fr or en")
        if body.password is not None:
            if account["id"] == OWNER:
                raise HTTPException(422, "The owner's password is MARGINOTE_PASSWORD, in the compose file")
            if not check_password(body.password.current, account.get("password")):
                time.sleep(1)
                raise HTTPException(403, "The current password is wrong")
        try:
            account = ctx.accounts.update(account["id"], name=body.name, language=body.language,
                                          password=body.password.new if body.password else None)
        except ValueError as err:
            raise HTTPException(422, str(err)) from None
        request.session.update(uid=account["id"], tag=ctx.session_tag(account))   # this device stays logged in
        return {"logged_in": True, **public(account)}

    # ----- accounts: the owner adds and removes people; nobody sees another's library -----

    @app.get("/api/accounts", tags=["account"])
    def list_accounts(_: dict = Depends(require_owner)):
        return [public(a) for a in ctx.accounts.all()]

    @app.post("/api/accounts", tags=["account"], status_code=201)
    def add_account(body: AccountIn, _: dict = Depends(require_owner)):
        """A new person, with an empty library of their own."""
        try:
            account = ctx.accounts.add(body.name, body.password, body.language)
        except ValueError as err:
            raise HTTPException(422, str(err)) from None
        ctx.library(account["id"])
        return public(account)

    @app.patch("/api/accounts/{account_id}", tags=["account"])
    def reset_password(account_id: str, body: AccountPatch, _: dict = Depends(require_owner)):
        """A new password for someone who forgot theirs; it logs them out everywhere."""
        try:
            return public(ctx.accounts.update(account_id, password=body.password))
        except KeyError:
            raise HTTPException(404, "No account with this id") from None
        except ValueError as err:
            raise HTTPException(422, str(err)) from None

    @app.delete("/api/accounts/{account_id}", tags=["account"])
    def remove_account(account_id: str, _: dict = Depends(require_owner)):
        """The person can no longer log in. Their library is kept on the NAS, set aside in
        data/users/removed/, in case it is needed again."""
        try:
            account = ctx.accounts.remove(account_id)
        except KeyError:
            raise HTTPException(404, "No account with this id") from None
        except ValueError as err:
            raise HTTPException(422, str(err)) from None
        ctx.forget_library(account_id)
        folder = ctx.folder_of(account_id)
        if folder.exists():
            aside = settings.data_dir / "users" / "removed"
            aside.mkdir(parents=True, exist_ok=True)
            folder.rename(aside / f"{account['id']}-{time.strftime('%Y-%m-%d')}")
        return {"removed": account_id}

    for module in (routes_library, routes_entries, routes_photos, routes_admin):
        app.include_router(module.router(ctx))

    app.mount("/static", StaticAssets(directory=STATIC), name="static")
    pages = {lang: page_html(lang) for lang in LANGUAGES}

    @app.get("/", include_in_schema=False)
    def app_page(request: Request):
        """In the language of whoever is logged in; before that, the last one chosen on this device, or the
        browser's."""
        account = ctx.account_for(request)
        lang = account.get("language") if account else request.cookies.get(LANG_COOKIE)
        if lang not in LANGUAGES:
            lang = "fr" if request.headers.get("accept-language", "").lower().startswith("fr") else "en"
        response = HTMLResponse(pages[lang], headers=PAGE_HEADERS)
        response.set_cookie(LANG_COOKIE, lang, max_age=365 * 24 * 3600, samesite="lax", secure=settings.cookie_secure)
        return response

    return app
