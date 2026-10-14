"""Shared per-client sign-in budgets."""
from alembic import op
import sqlalchemy as sa

revision = "b03_login_budgets"
down_revision = "b02_base_storage"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("login_budgets",
        sa.Column("client_hash", sa.String(64), primary_key=True),
        sa.Column("window", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False))
    op.create_index("ix_login_budgets_window", "login_budgets", ["window"])


def downgrade():
    op.drop_index("ix_login_budgets_window", table_name="login_budgets")
    op.drop_table("login_budgets")
