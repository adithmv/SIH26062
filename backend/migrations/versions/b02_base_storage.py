"""Device credentials and content hashes; existing files remain intact."""
from alembic import op
import sqlalchemy as sa

revision = "b02_base_storage"
down_revision = "b01_base_access"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("base_devices",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("active", sa.Boolean(), nullable=False))
    op.add_column("managed_files", sa.Column("sha256", sa.String(64)))
    op.add_column("prepared_files", sa.Column("sha256", sa.String(64)))


def downgrade():
    op.drop_column("prepared_files", "sha256")
    op.drop_column("managed_files", "sha256")
    op.drop_table("base_devices")
