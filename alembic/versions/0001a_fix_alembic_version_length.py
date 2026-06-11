"""fix alembic_version version_num column length

Revision ID: 0001a_fix_alembic_version_length
Revises: 0001_initial
Create Date: 2026-06-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001a_fix_alembic_version_length"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Expand the version_num column to accommodate long revision IDs
    op.alter_column(
        "alembic_version",
        "version_num",
        type_=sa.String(length=512),
        existing_type=sa.String(length=32),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Revert to original length
    op.alter_column(
        "alembic_version",
        "version_num",
        type_=sa.String(length=32),
        existing_type=sa.String(length=512),
        existing_nullable=False,
    )