"""add job_type column to jobs

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-10

Adds a job_type column ('video' or 'image') to the jobs table.
Existing rows are backfilled to 'video'.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.add_column(
            sa.Column("job_type", sa.String(20), nullable=False, server_default="video")
        )
    # Backfill: mark any job whose model is a known image model
    op.execute("UPDATE jobs SET job_type = 'image' WHERE model = 'pollojourney'")


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_column("job_type")
