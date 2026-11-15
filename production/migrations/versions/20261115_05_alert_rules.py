"""On-demand account-scoped portfolio alert thresholds.

Revision ID: 20261115_05
Revises: 20261115_04
"""
from alembic import op
import sqlalchemy as sa

revision='20261115_05'
down_revision='20261115_04'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('portfolio_alert_rules',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('portfolio_id',sa.String(36),sa.ForeignKey('portfolios.id',ondelete='CASCADE'),nullable=False),
        sa.Column('kind',sa.String(35),nullable=False),
        sa.Column('symbol',sa.String(16),nullable=False,server_default=''),
        sa.Column('threshold',sa.Float(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_portfolio_alert_rules_portfolio_id','portfolio_alert_rules',['portfolio_id'])


def downgrade():
    op.drop_index('ix_portfolio_alert_rules_portfolio_id',table_name='portfolio_alert_rules')
    op.drop_table('portfolio_alert_rules')
