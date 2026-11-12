"""OAuth sign-in routes: provider list, login redirect, callback, and `me`.

Logout is handled by the existing /api/auth/logout in api.py (it clears both the
API-key session and the user session).
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Request
from fastapi.responses import RedirectResponse

from web import users
from web.auth import set_user_cookie
from web.core.metadata import User, get_db
from web.dev_login import dev_login_enabled
from web.oauth import configured_providers, normalize_profile, oauth

router = APIRouter(prefix="/api/auth")


def _user_dict(u: User) -> dict[str, object]:
    return {
        "id": u.id,
        "email": u.email,
        "name": u.name,
        "avatar_url": u.avatar_url,
        "provider": u.provider,
        "is_admin": u.is_admin,
    }


def _redirect_uri(request: Request, provider: str) -> str:
    """Build the provider's callback URL.

    PUBLIC_BASE_URL pins the public HTTPS host; otherwise use the request URL.
    """
    base = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if base:
        return f"{base}/api/auth/callback/{provider}"
    return str(request.url_for("oauth_callback", provider=provider))


@router.get("/providers")
async def providers(user_session: Annotated[str | None, Cookie()] = None) -> dict[str, object]:
    """Return configured sign-in providers and the current user, if any."""
    user = users.resolve_current_user(user_session)
    return {
        "providers": configured_providers(),
        "open_signup": users.open_signup(),
        "dev_login": dev_login_enabled(),
        "user": _user_dict(user) if user else None,
    }


@router.get("/me")
async def me(user_session: Annotated[str | None, Cookie()] = None) -> dict[str, object]:
    """Return the signed-in user, if any."""
    user = users.resolve_current_user(user_session)
    return {"user": _user_dict(user) if user else None}


@router.get("/login/{provider}", name="oauth_login")
async def login(provider: str, request: Request) -> RedirectResponse:
    """Redirect to the selected OAuth provider."""
    if provider not in configured_providers():
        raise HTTPException(status_code=404, detail="Unknown or unconfigured provider")
    client = oauth.create_client(provider)
    return await client.authorize_redirect(request, _redirect_uri(request, provider))


@router.get("/callback/{provider}", name="oauth_callback")
async def callback(provider: str, request: Request) -> RedirectResponse:
    """Complete an OAuth sign-in and redirect to the application."""
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
    resp = RedirectResponse(url="/", status_code=302)
    set_user_cookie(resp, request, user.id)  # samesite=lax survives the redirect back
    return resp
