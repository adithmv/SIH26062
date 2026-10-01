"""PMCE retry state and shared sync lease."""
from alembic import op
import sqlalchemy as sa

revision = "1eaf002_pmce_delivery"
down_revision = "1eaf001_pmce"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("pmce_outbox", sa.Column("failures", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("pmce_outbox", sa.Column("next_attempt_at", sa.DateTime(timezone=True)))
    op.add_column("pmce_outbox", sa.Column("blocked", sa.Boolean(), nullable=False, server_default=sa.false()))
    lock = op.create_table(
        "pmce_sync_lock",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner", sa.Uuid()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(lock, [{"id": 1}])


def downgrade():
    op.drop_table("pmce_sync_lock")
    op.drop_column("pmce_outbox", "blocked")
    op.drop_column("pmce_outbox", "next_attempt_at")
    op.drop_column("pmce_outbox", "failures")
