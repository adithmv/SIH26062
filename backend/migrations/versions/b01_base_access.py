"""Base accounts, revocable sessions and access records."""
from alembic import op
import sqlalchemy as sa

revision = "b01_base_access"
down_revision = "aa6528c26a89"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("base_accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("username", sa.String(80), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True)))
    op.create_table("base_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("base_accounts.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_base_sessions_account_id", "base_sessions", ["account_id"])
    op.create_index("ix_base_sessions_expires_at", "base_sessions", ["expires_at"])
    op.create_table("access_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor", sa.String(80), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("target", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_access_events_created_at", "access_events", ["created_at"])


def downgrade():
    op.drop_table("access_events")
    op.drop_table("base_sessions")
    op.drop_table("base_accounts")
