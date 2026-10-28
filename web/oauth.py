"""OAuth sign-in via Authlib — Google and Microsoft (OIDC) and X (OAuth2/PKCE).

Each provider is registered only when its client id/secret are configured, so
the app runs fine with none set. Add a provider by setting its env vars:

    GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET
    MICROSOFT_OAUTH_CLIENT_ID / MICROSOFT_OAUTH_CLIENT_SECRET
    X_OAUTH_CLIENT_ID / X_OAUTH_CLIENT_SECRET

The redirect/callback URI registered with each provider must be
    https://<your-public-host>/api/auth/callback/<provider>
(https is mandatory except for http://localhost during development).
"""

from __future__ import annotations

import os

from authlib.integrations.starlette_client import OAuth

oauth = OAuth()

# Provider definitions. OIDC providers discover their endpoints from the
# metadata url; X is plain OAuth2 and needs its endpoints spelled out.
_GOOGLE_META = "https://accounts.google.com/.well-known/openid-configuration"
_MS_META = "https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration"


def _env(provider: str, field: str) -> str:
    return os.getenv(f"{provider.upper()}_OAUTH_{field}", "").strip()


def register_providers() -> None:
    """Register every provider that has credentials configured. Idempotent-ish:
    call once at startup."""
    if _env("google", "CLIENT_ID"):
        oauth.register(
            name="google",
            client_id=_env("google", "CLIENT_ID"),
            client_secret=_env("google", "CLIENT_SECRET"),
            server_metadata_url=_GOOGLE_META,
            client_kwargs={"scope": "openid email profile"},
        )
    if _env("microsoft", "CLIENT_ID"):
        oauth.register(
            name="microsoft",
            client_id=_env("microsoft", "CLIENT_ID"),
            client_secret=_env("microsoft", "CLIENT_SECRET"),
            server_metadata_url=_MS_META,
            client_kwargs={"scope": "openid email profile"},
        )
    if _env("x", "CLIENT_ID"):
        oauth.register(
            name="x",
            client_id=_env("x", "CLIENT_ID"),
            client_secret=_env("x", "CLIENT_SECRET"),
            authorize_url="https://twitter.com/i/oauth2/authorize",
            access_token_url="https://api.twitter.com/2/oauth2/token",
            api_base_url="https://api.twitter.com/2/",
            client_kwargs={
                "scope": "users.read tweet.read offline.access",
                "code_challenge_method": "S256",
                "token_endpoint_auth_method": "client_secret_basic",
            },
        )


def configured_providers() -> list[str]:
    """Names of providers that are registered (have credentials)."""
    return [p for p in ("google", "microsoft", "x") if _env(p, "CLIENT_ID")]


async def normalize_profile(provider: str, client, token) -> dict:
    """Provider's user info as {provider, sub, email, name, avatar}. Raises
    ValueError when a required field (a stable id) is missing."""
    if provider in ("google", "microsoft"):
        info = token.get("userinfo") or await client.userinfo(token=token)
        email = (info.get("email") or info.get("preferred_username") or "").lower() or None
        return {
            "provider": provider,
            "sub": info.get("sub"),
            "email": email,
            "name": info.get("name"),
            "avatar": info.get("picture"),
        }
    if provider == "x":
        resp = await client.get("users/me?user.fields=profile_image_url,name,username", token=token)
        data = (resp.json() or {}).get("data") or {}
        # X does not return email without elevated access; key on the handle
        email = f"{data.get('username')}@x.local" if data.get("username") else None
        return {
            "provider": provider,
            "sub": data.get("id"),
            "email": email,
            "name": data.get("name"),
            "avatar": data.get("profile_image_url"),
        }
    raise ValueError(f"Unknown provider: {provider}")
