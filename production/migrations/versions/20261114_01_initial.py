"""Frozen v0.4 schema baseline. Do not import live ORM metadata into migrations.

Revision ID: 20261114_01
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = '20261114_01'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'accounts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('email', sa.String(254), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_accounts_email', 'accounts', ['email'], unique=True)
    op.create_table(
        'login_sessions',
        sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('account_id', sa.String(36), sa.ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('csrf_hash', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_login_sessions_account_id', 'login_sessions', ['account_id'])
    op.create_table(
        'portfolios',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('account_id', sa.String(36), sa.ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(80), nullable=False),
        sa.Column('description', sa.String(255), nullable=False),
        sa.Column('kind', sa.String(10), nullable=False),
        sa.Column('is_demo', sa.Boolean(), nullable=False),
        sa.Column('cash', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_portfolios_account_id', 'portfolios', ['account_id'])
    op.create_table(
        'holdings',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('portfolio_id', sa.String(36), sa.ForeignKey('portfolios.id', ondelete='CASCADE'), nullable=False),
        sa.Column('symbol', sa.String(16), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('sector', sa.String(80), nullable=False),
        sa.Column('asset_class', sa.String(20), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('avg_cost', sa.Float(), nullable=False),
        sa.Column('current_price', sa.Float(), nullable=False),
        sa.UniqueConstraint('portfolio_id', 'symbol'),
    )
    op.create_index('ix_holdings_portfolio_id', 'holdings', ['portfolio_id'])
    op.create_table(
        'transactions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('portfolio_id', sa.String(36), sa.ForeignKey('portfolios.id', ondelete='CASCADE'), nullable=False),
        sa.Column('occurred_on', sa.Date(), nullable=False),
        sa.Column('kind', sa.String(12), nullable=False),
        sa.Column('symbol', sa.String(16), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('unit_price', sa.Float(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('memo', sa.String(240), nullable=False),
    )
    op.create_index('ix_transactions_portfolio_id', 'transactions', ['portfolio_id'])
    op.create_table(
        'prices',
        sa.Column('portfolio_id', sa.String(36), sa.ForeignKey('portfolios.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('symbol', sa.String(16), primary_key=True),
        sa.Column('trading_day', sa.Date(), primary_key=True),
        sa.Column('close', sa.Float(), nullable=False),
        sa.Column('source', sa.String(60), nullable=False),
    )
    op.create_table(
        'constituents',
        sa.Column('portfolio_id', sa.String(36), sa.ForeignKey('portfolios.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('fund_symbol', sa.String(16), primary_key=True),
        sa.Column('underlying_symbol', sa.String(16), primary_key=True),
        sa.Column('sector', sa.String(80), nullable=False),
        sa.Column('weight_pct', sa.Float(), nullable=False),
        sa.Column('as_of', sa.Date(), nullable=False),
        sa.Column('source', sa.String(180), nullable=False),
    )
    op.create_table(
        'securities',
        sa.Column('portfolio_id', sa.String(36), sa.ForeignKey('portfolios.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('symbol', sa.String(16), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('sector', sa.String(80), nullable=False),
        sa.Column('asset_class', sa.String(20), nullable=False),
    )


def downgrade():
    op.drop_table('securities')
    op.drop_table('constituents')
    op.drop_table('prices')
    op.drop_index('ix_transactions_portfolio_id', table_name='transactions')
    op.drop_table('transactions')
    op.drop_index('ix_holdings_portfolio_id', table_name='holdings')
    op.drop_table('holdings')
    op.drop_index('ix_portfolios_account_id', table_name='portfolios')
    op.drop_table('portfolios')
    op.drop_index('ix_login_sessions_account_id', table_name='login_sessions')
    op.drop_table('login_sessions')
    op.drop_index('ix_accounts_email', table_name='accounts')
    op.drop_table('accounts')
