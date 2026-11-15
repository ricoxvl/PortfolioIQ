"""Persist privacy-preserving failed login counters.

Revision ID: 20261114_02
Revises: 20261114_01
"""
from alembic import op
import sqlalchemy as sa

revision = '20261114_02'
down_revision = '20261114_01'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'login_failures',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('ip_hash', sa.String(64), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_login_failures_ip_hash', 'login_failures', ['ip_hash'])
    op.create_index('ix_login_failures_occurred_at', 'login_failures', ['occurred_at'])
    op.create_index('ix_login_failures_ip_when', 'login_failures', ['ip_hash', 'occurred_at'])


def downgrade():
    op.drop_index('ix_login_failures_ip_when', table_name='login_failures')
    op.drop_index('ix_login_failures_occurred_at', table_name='login_failures')
    op.drop_index('ix_login_failures_ip_hash', table_name='login_failures')
    op.drop_table('login_failures')
