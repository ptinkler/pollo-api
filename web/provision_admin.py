"""Provision the admin (owner) account — run on the host.

    python -m web.provision_admin --email you@gmail.com --set-password
    python -m web.provision_admin --email you@gmail.com --claim-orphans

Creates/promotes the admin, keyed on email (an OAuth login with the same email
resolves to this account). --set-password sets its email+password login;
--claim-orphans adopts pre-existing unowned data (and moves the legacy shared
library into the admin's folder).
"""

from __future__ import annotations

import argparse
import getpass

from img2vid.common.metadata import get_db


def main() -> None:
    ap = argparse.ArgumentParser(description="Create or promote the admin account.")
    ap.add_argument("--email", required=True, help="the owner's email (match your login address)")
    ap.add_argument("--name", default="Admin")
    ap.add_argument("--claim-orphans", action="store_true", help="assign unowned tenant rows to the admin")
    ap.add_argument("--set-password", action="store_true", help="set the admin's email+password login (prompts)")
    ap.add_argument("--password", help="password for --set-password (else prompts; avoid in shell history)")
    args = ap.parse_args()

    db = get_db()
    if args.set_password:
        from .passwords import hash_password

        pw = args.password or getpass.getpass("New admin password: ")
        if len(pw) < 10:
            raise SystemExit("Password must be at least 10 characters.")
        admin = db.create_local_admin(args.email, hash_password(pw), name=args.name)
    else:
        admin = db.ensure_admin(args.email, args.name)
    print(f"Admin: {admin.email}  (id {admin.id}, provider {admin.provider}, is_admin={admin.is_admin})")
    if args.claim_orphans:
        n = db.claim_orphans(admin.id)
        print(f"Assigned {n} previously-unowned row(s) to the admin.")
        moved = _migrate_library(admin.id)
        print(f"Moved {moved} legacy library upload(s) into the admin's folder.")


def _migrate_library(admin_id: str) -> int:
    """Move the shared (legacy) library uploads into the admin's per-user folder."""
    from img2vid.common import config

    base = config.ROOT_DIR / "library"
    if not base.is_dir():
        return 0
    dest = base / admin_id
    moved = 0
    for p in base.iterdir():
        if p.is_file():
            dest.mkdir(parents=True, exist_ok=True)
            p.rename(dest / p.name)
            moved += 1
    return moved


if __name__ == "__main__":
    main()
