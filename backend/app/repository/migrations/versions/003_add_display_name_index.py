"""add display name index

Revision ID: 003
Revises: 002
Create Date: 2026-11-01 00:15:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: str | Sequence[str] | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema: add index on garment.display_name for resolver lookups."""
    with op.batch_alter_table("garment", schema=None) as batch_op:
        batch_op.create_index("idx_garment_display_name", ["display_name"], unique=False)


def downgrade() -> None:
    """Downgrade schema: drop index on garment.display_name."""
    with op.batch_alter_table("garment", schema=None) as batch_op:
        batch_op.drop_index("idx_garment_display_name")

