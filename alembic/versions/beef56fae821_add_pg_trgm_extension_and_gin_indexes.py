"""add pg_trgm extension and GIN indexes

Revision ID: beef56fae821
Revises: fbcb6c5a7f9b
Create Date: 2026-05-23 09:40:52.998975

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'beef56fae821'
down_revision: Union[str, Sequence[str], None] = 'fbcb6c5a7f9b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # pg_trgm enables GIN trigram indexes for fast ILIKE/LIKE %wildcard% searches
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tickets_plate_trgm "
        "ON tickets USING GIN (license_plate gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tickets_location_trgm "
        "ON tickets USING GIN (location gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tickets_violation_trgm "
        "ON tickets USING GIN (violation gin_trgm_ops)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS idx_tickets_violation_trgm")
    op.execute("DROP INDEX IF EXISTS idx_tickets_location_trgm")
    op.execute("DROP INDEX IF EXISTS idx_tickets_plate_trgm")
