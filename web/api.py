"""
Pollo Studio — API Backend (FastAPI)

Run:  python web/app.py   (from the pollo root directory)
"""

import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import cv2
import uvicorn
from dotenv import load_dotenv
from fastapi import Cookie, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── Bootstrap ───────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parent.parent.resolve()
WEB_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT_DIR))
os.chdir(ROOT_DIR)
load_dotenv(override=True)

from web.core.get_task import get_credit_balance
from web.core.metadata import get_db

from . import characters, keyctx, media, vpn

# ── Authentication ───────────────────────────────────────────────────
from .auth import USER_COOKIE, make_user_session
from .chat import router as chat_router
from .chat import startup_resume_chat
from .chatgpt_import import router as chatgpt_import_router
from .users import require_user


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    # Startup: announce the auth posture so a misconfigured deploy is obvious
    from .users import admin_emails

    admins = admin_emails()
    if admins:
        print(f"🔒 Auth: email+password login for admin(s) {', '.join(sorted(admins))}; others via OAuth.")
    else:
        print("🔒 Auth: no ADMIN_EMAILS set — no one can create a local admin until it is configured.")
    # Register any OAuth providers that have credentials configured
    from .oauth import configured_providers, register_providers

    register_providers()
    providers = configured_providers()
    print(f"🔑 OAuth providers: {', '.join(providers) if providers else 'none configured'}")
    # Dev: seed the one-click dev account when enabled (no-op otherwise).
    from .dev_login import seed_dev_user

    seed_dev_user()
    startup_resume_chat()
    yield
    # Shutdown: nothing to do


def _bool_env(name: str, default: bool = False) -> bool:
    val = os.getenv(name, "").strip().lower()
    if val in {"1", "true", "yes", "on"}:
        return True
    if val in {"0", "false", "no", "off"}:
        return False
    return default


# The interactive API docs (/docs, /redoc, /openapi.json) expose the whole API
# surface unauthenticated, so they're off by default — enable with ENABLE_API_DOCS
# (or in dev, where DEV_LOGIN is set).
_docs_on = _bool_env("ENABLE_API_DOCS") or _bool_env("DEV_LOGIN")
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

from .auth import _user_secret  # noqa: E402

app.add_middleware(
    SessionMiddleware,
    secret_key=_user_secret().hex(),
    same_site="lax",
    https_only=_bool_env("COOKIE_SECURE", default=True),
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

        from http.cookies import SimpleCookie

        from web.core.metadata import reset_tenant, set_tenant

        from . import user_keys
        from .users import resolve_current_user

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


# ── Pydantic Models ─────────────────────────────────────────────────


class LoginRequest(BaseModel):
    email: str
    password: str


# ── Auth Routes ─────────────────────────────────────────────────────

COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days

# Login brute-force throttle: per-client-IP sliding window (in-memory).
LOGIN_MAX_ATTEMPTS = 10
LOGIN_WINDOW_SECONDS = 300
_login_attempts: dict[str, list[float]] = {}
_login_lock = threading.Lock()


def _cookie_secure(request: Request) -> bool:
    """Whether the session cookie should be marked Secure (HTTPS-only).

    Secure by default, so a TLS deployment (e.g. the NAS) needs no config. The
    one automatic exemption is plain-HTTP access to a loopback host, where
    local dev would otherwise break — browsers treat localhost as secure, so
    the cookie still works there. COOKIE_SECURE=true/false overrides either
    way: set it false only to serve auth over plain HTTP on a LAN."""
    override = os.getenv("COOKIE_SECURE", "").strip().lower()
    if override in {"1", "true", "yes", "on"}:
        return True
    if override in {"0", "false", "no", "off"}:
        return False
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    if request.url.scheme == "https" or forwarded == "https":
        return True
    host = (request.url.hostname or "").lower()
    return host not in {"localhost", "127.0.0.1", "::1"}


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


def _set_user_cookie(response: Response, request: Request, user_id: str) -> None:
    response.set_cookie(
        key=USER_COOKIE,
        value=make_user_session(user_id),
        httponly=True,
        samesite="lax",  # lax so the OAuth redirect back from the provider keeps it
        secure=_cookie_secure(request),
        max_age=COOKIE_MAX_AGE,
    )


@app.post("/api/auth/login")
async def api_auth_login(data: LoginRequest, response: Response, request: Request):
    email = data.email.strip().lower()
    if _login_rate_limited(request, email):
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
    from .passwords import needs_rehash, verify_password

    db = get_db()
    user = db.get_user_by_email(email)
    if not user or not user.password_hash or not verify_password(user.password_hash, data.password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if needs_rehash(user.password_hash):  # transparently upgrade to stronger params
        from .passwords import hash_password

        db.set_user_password(user.id, hash_password(data.password))
    _set_user_cookie(response, request, user.id)
    return {"ok": True, "email": user.email, "name": user.name}


@app.post("/api/auth/logout")
async def api_auth_logout(response: Response):
    response.delete_cookie(key=USER_COOKIE, samesite="lax")
    return {"ok": True}


@app.get("/api/auth/status")
async def api_auth_status(user_session: str | None = Cookie(None)):
    """Who (if anyone) is signed in. Admin accounts are created via the CLI
    (web.provision_admin), never through the app."""
    from .users import resolve_current_user

    user = resolve_current_user(user_session)
    return {
        "authenticated": user is not None,
        "user": {"email": user.email, "name": user.name, "is_admin": user.is_admin} if user else None,
    }


def _extract_first_frame_uncached(video_path: Path) -> bytes | None:
    """Extract the first frame from a video using OpenCV, returns JPEG bytes.
    No caching - always extracts fresh."""
    try:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return None
        ret, frame = cap.read()
        cap.release()
        if not ret or frame is None:
            return None
        _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return jpeg.tobytes()
    except Exception:
        return None


# Track jobs currently being recovered to prevent concurrent recovery attempts
_recovering_jobs: set[str] = set()
_recovering_lock = threading.Lock()


IMMUTABLE_CACHE = {"Cache-Control": "public, max-age=31536000, immutable"}


# ── Usage / Credit tracking ─────────────────────────────────────────


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


# ── Chat mode (OpenRouter) — see web/chat.py ─────────────────────────
# Must be registered before the SPA catch-all below.
from .dev_login import router as dev_login_router  # noqa: E402
from .oauth_routes import router as oauth_router  # noqa: E402
from .user_keys import router as keys_router  # noqa: E402

app.include_router(oauth_router)
app.include_router(keys_router)
app.include_router(dev_login_router)
app.include_router(chat_router)
app.include_router(chatgpt_import_router)
app.include_router(characters.router)
app.include_router(media.router)
app.include_router(vpn.router)


# ── Serve Vue frontend (production build) ────────────────────────────
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
