"""OAuth sign-in routes: provider list, login redirect, callback, and `me`.

Logout is handled by the existing /api/auth/logout in api.py (it clears both the
API-key session and the user session).
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Cookie, HTTPException, Request
from fastapi.responses import RedirectResponse

from img2vid.common.metadata import get_db

from . import users
from .auth import USER_COOKIE, make_user_session
from .dev_login import dev_login_enabled
from .oauth import configured_providers, normalize_profile, oauth

router = APIRouter(prefix="/api/auth")

USER_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def _user_dict(u) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "name": u.name,
        "avatar_url": u.avatar_url,
        "provider": u.provider,
        "is_admin": u.is_admin,
    }


def _redirect_uri(request: Request, provider: str) -> str:
    """The provider's callback URL. PUBLIC_BASE_URL pins the public https host
    (needed behind a reverse proxy / NAS); otherwise it's derived from request."""
    base = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if base:
        return f"{base}/api/auth/callback/{provider}"
    return str(request.url_for("oauth_callback", provider=provider))


@router.get("/providers")
async def providers(user_session: str | None = Cookie(None)):
    user = users.resolve_current_user(user_session)
    return {
        "providers": configured_providers(),
        "open_signup": users.open_signup(),
        "dev_login": dev_login_enabled(),
        "user": _user_dict(user) if user else None,
    }


@router.get("/me")
async def me(user_session: str | None = Cookie(None)):
    user = users.resolve_current_user(user_session)
    return {"user": _user_dict(user) if user else None}


@router.get("/login/{provider}", name="oauth_login")
async def login(provider: str, request: Request):
    if provider not in configured_providers():
        raise HTTPException(status_code=404, detail="Unknown or unconfigured provider")
    client = oauth.create_client(provider)
    return await client.authorize_redirect(request, _redirect_uri(request, provider))


@router.get("/callback/{provider}", name="oauth_callback")
async def callback(provider: str, request: Request):
    if provider not in configured_providers():
        raise HTTPException(status_code=404, detail="Unknown or unconfigured provider")
    client = oauth.create_client(provider)
    try:
        token = await client.authorize_access_token(request)
        profile = await normalize_profile(provider, client, token)
    except Exception as e:  # provider errors, denied consent, bad state
        raise HTTPException(status_code=400, detail=f"OAuth sign-in failed: {e}") from e
    if not profile.get("sub") or not profile.get("email"):
        raise HTTPException(status_code=400, detail="Provider did not return a usable profile (id/email)")

    db = get_db()
    allowed, is_admin = users.admit(profile["email"], is_first_user=db.count_users() == 0)
    if not allowed:
        return RedirectResponse(url="/?auth=denied", status_code=302)

    user = db.upsert_oauth_user(profile, is_admin=is_admin)
    from .api import _cookie_secure  # lazy: avoid an import cycle with api.py

    resp = RedirectResponse(url="/", status_code=302)
    resp.set_cookie(
        key=USER_COOKIE,
        value=make_user_session(user.id),
        httponly=True,
        samesite="lax",  # must survive the cross-site redirect back from the provider
        secure=_cookie_secure(request),
        max_age=USER_COOKIE_MAX_AGE,
    )
    return resp
