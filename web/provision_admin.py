"""Provision the admin (owner) account — run on the host.

    python -m web.provision_admin --email you@gmail.com
    python -m web.provision_admin --email you@gmail.com --claim-orphans

Creates the user with that email as admin, or promotes an existing one. The
account is keyed on email, so signing in later with Google (same address) — or
with the LAN access key — resolves to this same account and its data.

--claim-orphans assigns any tenant rows with no owner to the admin (useful
right after the 0020 migration or a data import). The 0020 migration already
backfills existing rows to the admin; this is the belt-and-braces / re-run.
"""

from __future__ import annotations

import argparse

from img2vid.common.metadata import get_db


def main() -> None:
    ap = argparse.ArgumentParser(description="Create or promote the admin account.")
    ap.add_argument("--email", required=True, help="the owner's email (match your Google address)")
    ap.add_argument("--name", default="Admin")
    ap.add_argument("--claim-orphans", action="store_true", help="assign unowned tenant rows to the admin")
    args = ap.parse_args()

    db = get_db()
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
