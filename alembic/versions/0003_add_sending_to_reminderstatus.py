"""add sending status to reminderstatus enum

Revision ID: 0003_add_sending_to_reminderstatus
Revises: 0002_add_ondelete_cascade_to_reminders
Create Date: 2026-05-02 11:11:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0003_add_sending_to_reminderstatus"
down_revision = "0002_add_ondelete_cascade_to_reminders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The initial migration created enum values: SCHEDULED, SENT, FAILED, CANCELED
    # We need to add the SENDING value that the Python code expects
    op.execute("ALTER TYPE reminderstatus ADD VALUE 'SENDING'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values directly
    # This would require recreating the type and table, which is complex
    # For now, we leave the value in place
    pass