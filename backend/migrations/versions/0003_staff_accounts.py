"""Create per-person staff accounts with password hashes."""
from alembic import op
import sqlalchemy as sa

revision="0003_staff"
down_revision="0002_lifecycle"
branch_labels=None
depends_on=None

def upgrade():
    if not sa.inspect(op.get_bind()).has_table("auth_users"):
        op.create_table("auth_users",
            sa.Column("id",sa.Integer(),primary_key=True),
            sa.Column("username",sa.String(),nullable=False,unique=True),
            sa.Column("password_hash",sa.String(),nullable=False),
            sa.Column("role",sa.String(),nullable=False),
            sa.Column("active",sa.Boolean(),nullable=False),
            sa.Column("auth_version",sa.Integer(),nullable=False),
            sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
            sa.Column("last_login_at",sa.DateTime(timezone=True),nullable=True))
        op.create_index("ix_auth_users_username","auth_users",["username"],unique=True)
        op.create_index("ix_auth_users_role","auth_users",["role"])

def downgrade():
    op.drop_index("ix_auth_users_role",table_name="auth_users")
    op.drop_index("ix_auth_users_username",table_name="auth_users")
    op.drop_table("auth_users")
