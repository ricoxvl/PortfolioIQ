"""Per-portfolio benchmark research bars and account-scoped provider use limits.

Revision ID: 20261115_03
Revises: 20261114_02
"""
from alembic import op
import sqlalchemy as sa

revision = '20261115_03'
down_revision = '20261114_02'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('market_benchmark_bars',
        sa.Column('portfolio_id',sa.String(36),sa.ForeignKey('portfolios.id',ondelete='CASCADE'),primary_key=True),
        sa.Column('symbol',sa.String(16),primary_key=True),
        sa.Column('trading_day',sa.Date(),primary_key=True),
        sa.Column('close',sa.Float(),nullable=False),
        sa.Column('source',sa.String(180),nullable=False),
        sa.Column('adjustment',sa.String(10),nullable=False),
        sa.Column('imported_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('market_fetch_attempts',
        sa.Column('id',sa.Integer(),primary_key=True,autoincrement=True),
        sa.Column('account_id',sa.String(36),sa.ForeignKey('accounts.id',ondelete='CASCADE'),nullable=False),
        sa.Column('occurred_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_market_fetch_attempts_account_id','market_fetch_attempts',['account_id'])
    op.create_index('ix_market_fetch_attempts_occurred_at','market_fetch_attempts',['occurred_at'])


def downgrade():
    op.drop_index('ix_market_fetch_attempts_occurred_at',table_name='market_fetch_attempts')
    op.drop_index('ix_market_fetch_attempts_account_id',table_name='market_fetch_attempts')
    op.drop_table('market_fetch_attempts')
    op.drop_table('market_benchmark_bars')