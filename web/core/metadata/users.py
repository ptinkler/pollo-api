"""User accounts (OAuth + local admin) and tenant-ownership claiming."""

import uuid
from datetime import datetime

from .models import User
from .tenant import TENANT_MODELS


class UserMixin:
    def get_user(self, user_id: str) -> User | None:
        with self._session() as session:
            user = session.get(User, user_id)
            if user:
                session.expunge(user)
            return user

    def get_user_by_email(self, email: str) -> User | None:
        with self._session() as session:
            user = session.query(User).filter(User.email == email.lower()).first()
            if user:
                session.expunge(user)
            return user

    def get_user_by_provider(self, provider: str, provider_sub: str) -> User | None:
        with self._session() as session:
            user = session.query(User).filter(User.provider == provider, User.provider_sub == provider_sub).first()
            if user:
                session.expunge(user)
            return user

    def upsert_oauth_user(self, profile: dict, is_admin: bool = False) -> User:
        """Create or refresh a user from an OAuth profile {provider, sub, email,
        name, avatar}. Matches on (provider, sub) first, then email."""
        with self._session() as session:
            user = (
                session.query(User)
                .filter(User.provider == profile["provider"], User.provider_sub == profile["sub"])
                .first()
            )
            if not user and profile.get("email"):
                user = session.query(User).filter(User.email == profile["email"]).first()
            if user:
                user.name = profile.get("name") or user.name
                user.avatar_url = profile.get("avatar") or user.avatar_url
                user.provider = profile["provider"]
                user.provider_sub = profile["sub"]
                user.last_login_at = datetime.now()
                if is_admin:
                    user.is_admin = True
            else:
                user = User(
                    id=uuid.uuid4().hex,
                    email=profile["email"],
                    name=profile.get("name"),
                    avatar_url=profile.get("avatar"),
                    provider=profile["provider"],
                    provider_sub=profile["sub"],
                    is_admin=is_admin,
                    last_login_at=datetime.now(),
                )
                session.add(user)
            session.commit()
            session.refresh(user)
            session.expunge(user)
            return user

    def count_users(self) -> int:
        with self._session() as session:
            return session.query(User).count()

    def ensure_admin(self, email: str, name: str = "Admin") -> User:
        """Create the user with this email as admin, or promote an existing one
        (without changing their sign-in provider)."""
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
        """Assign every tenant row that has no owner to this user. For setup /
        after an import; runs with no tenant bound, so it sees all rows."""
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
        """Store the user's source-media hosting preferences (plain JSON, or
        None to fall back to the instance default)."""
        with self._session() as session:
            user = session.get(User, user_id)
            if user:
                user.upload_prefs_json = upload_prefs_json
                session.commit()

    def list_api_key_blobs(self) -> list[str]:
        """Every stored api_keys_json across all users (non-empty), for deciding
        whether the DB already holds encrypted key material."""
        with self._session() as session:
            return [b for (b,) in session.query(User.api_keys_json).filter(User.api_keys_json.isnot(None)) if b]

    def create_local_admin(self, email: str, password_hash: str, name: str = "Admin") -> User:
        """Create (or promote + set the password of) a local email+password admin
        account. Caller enforces that the email is an allowed admin email."""
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
