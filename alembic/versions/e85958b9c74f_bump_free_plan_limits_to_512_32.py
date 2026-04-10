"""bump free plan limits to 512/32

Revision ID: e85958b9c74f
Revises: fc514e89a7c1
Create Date: 2026-03-05 13:31:14.400018

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e85958b9c74f"
down_revision: Union[str, Sequence[str], None] = "fc514e89a7c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Update the FREE plan limits (plan_id = 1)
    op.execute(
        """
        UPDATE plan_limits
        SET max_n = 512,
            max_k = 32,
            updated_at = NOW()
        WHERE plan_id = 1;
    """
    )


def downgrade() -> None:
    # Revert to original values
    op.execute(
        """
        UPDATE plan_limits
        SET max_n = 256,
            max_k = 16,
            updated_at = NOW()
        WHERE plan_id = 1;
    """
    )
