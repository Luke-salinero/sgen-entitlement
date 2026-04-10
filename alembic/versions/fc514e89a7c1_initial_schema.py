import sqlalchemy as sa

from alembic import op

revision = "fc514e89a7c1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tier", sa.Text, nullable=False, unique=True),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("allow_live", sa.Boolean, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    op.create_table(
        "plan_limits",
        sa.Column(
            "plan_id",
            sa.Integer,
            sa.ForeignKey("plans.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("max_n", sa.Integer, nullable=False),
        sa.Column("max_k", sa.Integer, nullable=False),
        sa.Column("existential_only", sa.Boolean, nullable=False),
        sa.Column("rate_limit", sa.Integer, nullable=False),
        sa.Column("rate_window", sa.Integer, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    # NOTE: If you want snake_case, use user_id/api_key/account_name instead.
    # If you keep camelCase, you MUST quote in SQL forever.
    op.create_table(
        "subjects",
        sa.Column("userID", sa.Text, primary_key=True),
        sa.Column("apiKey", sa.Text, nullable=False),
        sa.Column("accountName", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    op.create_table(
        "subject_plan",
        sa.Column(
            "subject_id",
            sa.Text,
            sa.ForeignKey("subjects.userID", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "plan_id",
            sa.Integer,
            sa.ForeignKey("plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
    )

    op.create_table(
        "subject_plan_limits",
        sa.Column(
            "subject_id",
            sa.Text,
            sa.ForeignKey("subjects.userID", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("max_n", sa.Integer, nullable=False),
        sa.Column("max_k", sa.Integer, nullable=False),
        sa.Column("existential_only", sa.Boolean, nullable=False),
        sa.Column("rate_limit", sa.Integer, nullable=False),
        sa.Column("rate_window", sa.Integer, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    # Seed plans
    op.execute(
        """
        INSERT INTO plans (id, tier, status, allow_live, description)
        VALUES
          (1, 'free',   'active', false, 'Free tier'),
          (2, 'pro',    'active', true,  'Pro tier'),
          (3, 'custom', 'active', true,  'Custom tier')
        ON CONFLICT (id) DO NOTHING;
    """
    )

    op.execute(
        """
        INSERT INTO plan_limits (plan_id, max_n, max_k, existential_only,
        rate_limit, rate_window)
        VALUES
          (1, 256,  16, true,  60,   60),
          (2, 1024, 64, false, 600,  60),
          (3, 2048, 256,false, 6000, 60)
        ON CONFLICT (plan_id) DO NOTHING;
    """
    )


def downgrade() -> None:
    op.drop_table("subject_plan_limits")
    op.drop_table("subject_plan")
    op.drop_table("subjects")
    op.drop_table("plan_limits")
    op.drop_table("plans")
