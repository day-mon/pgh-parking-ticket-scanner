"""add composite index on issue_date and status

Allows status='open' + year range scans to use a single index
instead of scanning issue_date and filtering status in memory.

Revision ID: 5bdb0e612f76
Revises: beef56fae821
Create Date: 2026-05-23 09:51:58.663842

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5bdb0e612f76'
down_revision: Union[str, Sequence[str], None] = 'beef56fae821'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        "idx_tickets_issue_date_status",
        "tickets",
        ["issue_date", "status"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_tickets_issue_date_status", table_name="tickets")
