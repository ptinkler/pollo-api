"""baseline

Revision ID: 0001
Revises:
Create Date: 2026-05-24

Schema is created by SQLAlchemy create_all() on first run.
This revision marks the current schema as the starting point.
Existing deployments: run `alembic stamp 0001` to register this baseline.
"""
from typing import Sequence, Union

revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
