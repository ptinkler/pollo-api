"""add generation_favourites

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-06

Starred generations (per media file), shown in the home page's Favourites tab.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # MetadataDB() creates tables on startup too, so skip it if it's there
    if "generation_favourites" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "generation_favourites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("job_id", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_generation_favourites_filename", "generation_favourites", ["filename"], unique=True)
    op.create_index("ix_generation_favourites_job_id", "generation_favourites", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_generation_favourites_job_id", table_name="generation_favourites")
    op.drop_index("ix_generation_favourites_filename", table_name="generation_favourites")
    op.drop_table("generation_favourites")
