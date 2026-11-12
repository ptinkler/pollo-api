"""User accounts (OAuth + local admin) and tenant-ownership claiming."""

import uuid
from collections.abc import Mapping
from datetime import datetime

from web.core.metadata._base import DBBase
from web.core.metadata.models import User
from web.core.metadata.tenant import TENANT_MODELS


class UserMixin(DBBase):
    """Provide user-account and tenant-ownership operations."""

    def get_user(self, user_id: str) -> User | None:
        """Return a user by id, or ``None`` if it does not exist."""
        with self._session() as session:
            user = session.get(User, user_id)
            if user:
                session.expunge(user)
            return user

    def get_user_by_email(self, email: str) -> User | None:
        """Return a user by case-insensitive email address, if present."""
        with self._session() as session:
            user = session.query(User).filter(User.email == email.lower()).first()
            if user:
                session.expunge(user)
            return user

    def upsert_oauth_user(self, profile: Mapping[str, str | None], is_admin: bool = False) -> User:
        """Create or refresh a user from an OAuth profile.

        The profile contains ``provider``, ``sub``, ``email``, ``name``, and
        ``avatar``. Users match on ``(provider, sub)`` first, then email.
        """
        provider, sub, email = (profile.get(key) for key in ("provider", "sub", "email"))
        if not isinstance(provider, str) or not isinstance(sub, str) or not isinstance(email, str):
            raise TypeError(profile)

        with self._session() as session:
            user = session.query(User).filter(User.provider == provider, User.provider_sub == sub).first()
            if not user:
                user = session.query(User).filter(User.email == email).first()
            if user:
                user.name = profile.get("name") or user.name
                user.avatar_url = profile.get("avatar") or user.avatar_url
                user.provider = provider
                user.provider_sub = sub
                user.last_login_at = datetime.now().astimezone().replace(tzinfo=None)
                if is_admin:
                    user.is_admin = True
            else:
                user = User(
                    id=uuid.uuid4().hex,
                    email=email,
                    name=profile.get("name"),
                    avatar_url=profile.get("avatar"),
                    provider=provider,
                    provider_sub=sub,
                    is_admin=is_admin,
                    last_login_at=datetime.now().astimezone().replace(tzinfo=None),
                )
                session.add(user)
            session.commit()
            session.refresh(user)
            session.expunge(user)
            return user

    def count_users(self) -> int:
        """Return the number of registered users."""
        with self._session() as session:
            return session.query(User).count()

    def ensure_admin(self, email: str, name: str = "Admin") -> User:
        """Create or promote an administrator account.

        Promoting an existing user does not change their sign-in provider.
        """
        with self._session() as session:
            user = session.query(User).filter(User.email == email.lower()).first()
            if user:
                user.is_admin = True
            else:
                user = User(
                    id=uuid.uuid4().hex,
                    email=email.lower(),
                    name=name,
                    provider="local",
                    provider_sub="admin",
                    is_admin=True,
                )
                session.add(user)
            session.commit()
            session.refresh(user)
            session.expunge(user)
            return user

    def claim_orphans(self, user_id: str) -> int:
        """Assign all unowned tenant rows to this user.

        Used during setup or after an import; without a tenant bound, all rows
        are visible.
        """
        count = 0
        with self._session() as session:
            for model in TENANT_MODELS:
                count += session.query(model).filter(model.user_id.is_(None)).update({model.user_id: user_id}) or 0
            session.commit()
        return count

    def set_user_api_keys(self, user_id: str, api_keys_json: str | None) -> None:
        """Store the user's (encrypted) provider keys blob."""
        with self._session() as session:
            user = session.get(User, user_id)
            if user:
                user.api_keys_json = api_keys_json
                session.commit()

    def set_user_upload_prefs(self, user_id: str, upload_prefs_json: str | None) -> None:
        """Store source-media hosting preferences for a user.

        Pass ``None`` to use the instance default.
        """
        with self._session() as session:
            user = session.get(User, user_id)
            if user:
                user.upload_prefs_json = upload_prefs_json
                session.commit()

    def list_api_key_blobs(self) -> list[str]:
        """Return non-empty API-key blobs stored for all users.

        Used to determine whether the database already contains encrypted keys.
        """
        with self._session() as session:
            return [user.api_keys_json for user in session.query(User) if user.api_keys_json]

    def create_local_admin(self, email: str, password_hash: str, name: str = "Admin") -> User:
        """Create or update a local email-and-password administrator.

        The caller enforces that the email is allowed for administration.
        """
        with self._session() as session:
            user = session.query(User).filter(User.email == email.lower()).first()
            if not user:
                user = User(
                    id=uuid.uuid4().hex,
                    email=email.lower(),
                    name=name,
                    provider="local",
                    provider_sub="admin",
                    is_admin=True,
                )
                session.add(user)
            user.is_admin = True
            user.password_hash = password_hash
            session.commit()
            session.refresh(user)
            session.expunge(user)
            return user

    def set_user_password(self, user_id: str, password_hash: str) -> None:
        """Replace a user's stored password hash (e.g. after a transparent rehash)."""
        with self._session() as session:
            user = session.get(User, user_id)
            if user:
                user.password_hash = password_hash
                session.commit()
