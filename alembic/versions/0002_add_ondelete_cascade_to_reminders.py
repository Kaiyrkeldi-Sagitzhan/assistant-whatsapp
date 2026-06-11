"""Add ondelete=CASCADE to reminders.task_id foreign key

Revision ID: 0002_add_ondelete_cascade_to_reminders
Revises: 0001_initial
Create Date: 2026-04-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002_add_ondelete_cascade_to_reminders"
down_revision = "0001a_fix_alembic_version_length"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the existing foreign key constraint
    op.drop_constraint("reminders_task_id_fkey", "reminders", type_="foreignkey")
    
    # Create new foreign key constraint with ondelete=CASCADE
    op.create_foreign_key(
        "reminders_task_id_fkey",
        "reminders",
        "tasks",
        ["task_id"],
        ["id"],
        ondelete="CASCADE"
    )


def downgrade() -> None:
    # Drop the foreign key constraint with ondelete
    op.drop_constraint("reminders_task_id_fkey", "reminders", type_="foreignkey")
    
    # Recreate the original foreign key constraint without ondelete
    op.create_foreign_key(
        "reminders_task_id_fkey",
        "reminders",
        "tasks",
        ["task_id"],
        ["id"]
    )
