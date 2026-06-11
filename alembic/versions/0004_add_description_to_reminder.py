"""add description to reminder

Revision ID: 0004_add_description_to_reminder
Revises: 0003_add_sending_to_reminderstatus
Create Date: 2026-05-21 10:47:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0004_add_description_to_reminder"
down_revision = "0003_add_sending_to_reminderstatus"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reminders", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("reminders", "description")