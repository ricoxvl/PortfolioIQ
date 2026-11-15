"""Authenticated issuer snapshots and unadjusted price source audit.

Revision ID: 20261115_04
Revises: 20261115_03
"""
from alembic import op
import sqlalchemy as sa

revision='20261115_04'
down_revision='20261115_03'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('issuer_verified_snapshots',
        sa.Column('portfolio_id',sa.String(36),sa.ForeignKey('portfolios.id',ondelete='CASCADE'),primary_key=True),
        sa.Column('fund_symbol',sa.String(16),primary_key=True),
        sa.Column('issuer',sa.String(100),nullable=False),
        sa.Column('source_url',sa.String(360),nullable=False),
        sa.Column('source_sha256',sa.String(64),nullable=False),
        sa.Column('as_of',sa.Date(),nullable=False),
        sa.Column('position_count',sa.Integer(),nullable=False),
        sa.Column('mapped_weight_pct',sa.Float(),nullable=False),
        sa.Column('excluded_weight_pct',sa.Float(),nullable=False),
        sa.Column('verified_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('price_import_audits',
        sa.Column('portfolio_id',sa.String(36),sa.ForeignKey('portfolios.id',ondelete='CASCADE'),primary_key=True),
        sa.Column('symbol',sa.String(16),primary_key=True),
        sa.Column('provider',sa.String(100),nullable=False),
        sa.Column('source_sha256',sa.String(64),nullable=False),
        sa.Column('adjustment',sa.String(12),nullable=False),
        sa.Column('observations',sa.Integer(),nullable=False),
        sa.Column('last_date',sa.Date(),nullable=False),
        sa.Column('fetched_at',sa.DateTime(timezone=True),nullable=False))


def downgrade():
    op.drop_table('price_import_audits')
    op.drop_table('issuer_verified_snapshots')