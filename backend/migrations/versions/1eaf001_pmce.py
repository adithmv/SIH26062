"""Add PMCE outbox and central receipts."""
from alembic import op
import sqlalchemy as sa

revision = "1eaf001_pmce"
down_revision = "911a743ebba4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pmce_outbox",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event", sa.JSON(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(250)),
    )
    op.create_table(
        "pmce_receipts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("pmce_receipts")
    op.drop_table("pmce_outbox")
