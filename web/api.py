"""
Pollo Studio — API Backend (FastAPI)

Run:  make dev-api   (uvicorn web.api:app, from the repo root)
"""

import logging
import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from http.cookies import SimpleCookie
from pathlib import Path

import uvicorn
from fastapi import Cookie, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT_DIR = Path(__file__).parent.parent.resolve()
WEB_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT_DIR))
os.chdir(ROOT_DIR)

from web.core import config  # noqa: E402, F401 — imported first: loads .env before anything reads it
from web.core.logs import setup as _setup_logging  # noqa: E402

_setup_logging()
log = logging.getLogger(__name__)
from web.core.env import bool_env  # noqa: E402
from web.core.get_task import get_credit_balance
from web.core.metadata import get_db, reset_tenant, set_tenant
from web.core.metadata.schema import ensure_schema

from . import characters, keyctx, media, user_keys, vpn
from .auth import USER_COOKIE, set_user_cookie
from .chat import router as chat_router
from .chat import startup_resume_chat
from .chatgpt_import import router as chatgpt_import_router
from .dev_login import seed_dev_user
from .oauth import configured_providers, register_providers
from .passwords import hash_password, needs_rehash, verify_password
from .users import admin_emails, require_user, resolve_current_user


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    # Startup: announce the auth posture so a misconfigured deploy is obvious
    admins = admin_emails()
    if admins:
        log.info("auth: email+password login for admin(s) %s; others via OAuth", ", ".join(sorted(admins)))
    else:
        log.warning("auth: no ADMIN_EMAILS set — no one can create a local admin until it is configured")
    # Register any OAuth providers that have credentials configured
    register_providers()
    providers = configured_providers()
    log.info("OAuth providers: %s", ", ".join(providers) if providers else "none configured")
    # Alembic owns the schema; bring it up to date before anything reads it.
    db = get_db()
    ensure_schema(db.engine, db.db_path, fresh=getattr(db, "_fresh", False))
    # Dev: seed the one-click dev account when enabled (no-op otherwise).
    seed_dev_user()
    startup_resume_chat()
    yield
    # Shutdown: nothing to do


# The interactive API docs (/docs, /redoc, /openapi.json) expose the whole API
# surface unauthenticated, so they're off by default — enable with ENABLE_API_DOCS
# (or in dev, where DEV_LOGIN is set).
_docs_on = bool_env("ENABLE_API_DOCS") or bool_env("DEV_LOGIN")
app = FastAPI(
    title="Pollo Studio API",
    lifespan=lifespan,
    docs_url="/docs" if _docs_on else None,
    redoc_url="/redoc" if _docs_on else None,
    openapi_url="/openapi.json" if _docs_on else None,
)

# CORS - allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://localhost:5173",
        "https://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session middleware holds Authlib's transient OAuth state across the redirect.
# SameSite=lax so the state cookie survives the return hop from the provider;
# Secure (https_only) by default, matching the login cookie — disable only for
# plain-HTTP LAN dev via COOKIE_SECURE=false.
from starlette.middleware.sessions import SessionMiddleware  # noqa: E402

from .auth import user_secret  # noqa: E402

app.add_middleware(
    SessionMiddleware,
    secret_key=user_secret().hex(),
    same_site="lax",
    https_only=bool_env("COOKIE_SECURE", default=True),
)


class UserContextMiddleware:
    """Bind the signed-in user's provider keys AND tenant for the whole request,
    the streamed response body included. A pure ASGI middleware (not
    BaseHTTPMiddleware) is required: its context survives into the response
    streaming, where chat turns run and would otherwise see no keys/tenant."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api"):
            return await self.app(scope, receive, send)

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        jar = SimpleCookie()
        jar.load(headers.get("cookie", ""))
        cookie = lambda name: jar[name].value if name in jar else None  # noqa: E731

        user = resolve_current_user(cookie("user_session"))
        ktoken = keyctx.set_keys(user_keys.get_user_keys(user) if user else {})
        # "" owns no rows, so an unauthenticated API call sees no tenant data
        # (with None the scope filter would be bypassed entirely).
        ttoken = set_tenant(user.id if user else "")
        try:
            await self.app(scope, receive, send)
        finally:
            keyctx.reset_keys(ktoken)
            reset_tenant(ttoken)


app.add_middleware(UserContextMiddleware)


class LoginRequest(BaseModel):
    email: str
    password: str


# Login brute-force throttle: per-client-IP sliding window (in-memory).
LOGIN_MAX_ATTEMPTS = 10
LOGIN_WINDOW_SECONDS = 300
_login_attempts: dict[str, list[float]] = {}
_login_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    """The real client IP. Behind the reverse proxy, request.client is the
    proxy, so prefer the IP nginx stamps (X-Real-IP; it overwrites any client
    value), then the first X-Forwarded-For hop, then the socket peer."""
    real = request.headers.get("x-real-ip", "").strip()
    if real:
        return real
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else "unknown"


def _record_attempt(key: str, now: float) -> bool:
    """Append an attempt under `key` (caller holds the lock); True if over the limit."""
    attempts = [t for t in _login_attempts.get(key, []) if now - t < LOGIN_WINDOW_SECONDS]
    attempts.append(now)
    _login_attempts[key] = attempts
    return len(attempts) > LOGIN_MAX_ATTEMPTS


def _login_rate_limited(request: Request, email: str) -> bool:
    """Record this login attempt and report whether the client IP OR the target
    account is over the limit. Keying on the email too means spoofing the
    X-Forwarded-For / X-Real-IP headers can't lift the per-account cap."""
    now = time.time()
    with _login_lock:
        over_ip = _record_attempt(f"ip:{_client_ip(request)}", now)
        over_email = _record_attempt(f"email:{email}", now)
        # Opportunistically drop idle keys so the map can't grow unbounded.
        if len(_login_attempts) > 2048:
            for k in [k for k, ts in _login_attempts.items() if all(now - t >= LOGIN_WINDOW_SECONDS for t in ts)]:
                _login_attempts.pop(k, None)
        return over_ip or over_email


@app.post("/api/auth/login")
async def api_auth_login(data: LoginRequest, response: Response, request: Request):
    email = data.email.strip().lower()
    if _login_rate_limited(request, email):
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
    db = get_db()
    user = db.get_user_by_email(email)
    if not user or not user.password_hash or not verify_password(user.password_hash, data.password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if needs_rehash(user.password_hash):  # transparently upgrade to stronger params
        db.set_user_password(user.id, hash_password(data.password))
    set_user_cookie(response, request, user.id)
    return {"ok": True, "email": user.email, "name": user.name}


@app.post("/api/auth/logout")
async def api_auth_logout(response: Response):
    response.delete_cookie(key=USER_COOKIE, samesite="lax")
    return {"ok": True}


@app.get("/api/auth/status")
async def api_auth_status(user_session: str | None = Cookie(None)):
    """Who (if anyone) is signed in. Admin accounts are created via the CLI
    (web.provision_admin), never through the app."""
    user = resolve_current_user(user_session)
    return {
        "authenticated": user is not None,
        "user": {"email": user.email, "name": user.name, "is_admin": user.is_admin} if user else None,
    }


# Track jobs currently being recovered to prevent concurrent recovery attempts
_recovering_jobs: set[str] = set()
_recovering_lock = threading.Lock()


IMMUTABLE_CACHE = {"Cache-Control": "public, max-age=31536000, immutable"}


@app.get("/api/usage/balance")
def api_usage_balance(_api_key: str = Depends(require_user)):
    """Fetch current credit balance from the Pollo API."""
    api_key = keyctx.provider_key("pollo")
    if not api_key:
        raise HTTPException(status_code=500, detail="API key not configured")

    balance = get_credit_balance(api_key)
    if balance is None:
        raise HTTPException(status_code=502, detail="Failed to fetch credit balance from Pollo API")

    return balance


# Must be registered before the SPA catch-all below.
from .dev_login import router as dev_login_router  # noqa: E402
from .oauth_routes import router as oauth_router  # noqa: E402
from .public_media import router as public_media_router  # noqa: E402
from .upload_settings import router as upload_settings_router  # noqa: E402
from .user_keys import router as keys_router  # noqa: E402

app.include_router(oauth_router)
app.include_router(keys_router)
app.include_router(upload_settings_router)
app.include_router(public_media_router)
app.include_router(dev_login_router)
app.include_router(chat_router)
app.include_router(chatgpt_import_router)
app.include_router(characters.router)
app.include_router(media.router)
app.include_router(vpn.router)


STATIC_DIR = WEB_DIR / "static"


def _static_file(path: str, static_dir: Path = STATIC_DIR) -> Path:
    """Map a request path to a file in the SPA build, falling back to index.html.

    Resolved and confined to static_dir: encoded "../" (e.g. /..%2F.env)
    reaches us un-normalised and would otherwise escape the directory.
    """
    file = (static_dir / path).resolve()
    if file.is_relative_to(static_dir.resolve()) and file.is_file():
        return file
    return static_dir / "index.html"


if STATIC_DIR.is_dir():
    # Serve static assets (js, css, etc.)
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="static-assets")

    @app.get("/{path:path}")
    def serve_frontend(path: str):
        """Catch-all: serve the Vue SPA index.html for any non-API route."""
        return FileResponse(_static_file(path))


if __name__ == "__main__":
    print("Starting Pollo API Server...")
    print("API: http://localhost:5000")
    print("Docs: http://localhost:5000/docs")
    uvicorn.run(app, host="127.0.0.1", port=5000)
