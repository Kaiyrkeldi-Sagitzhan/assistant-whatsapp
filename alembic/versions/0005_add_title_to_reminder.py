"""add title to reminder

Revision ID: 0005_add_title_to_reminder
Revises: 0004_add_description_to_reminder
Create Date: 2026-06-21 13:45:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0005_add_title_to_reminder"
down_revision = "0004_add_description_to_reminder"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reminders", sa.Column("title", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("reminders", "title")