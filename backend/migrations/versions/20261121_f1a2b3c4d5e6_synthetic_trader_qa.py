"""synthetic trader QA: runs, deduplicated issues, ticker ledger

Revision ID: f1a2b3c4d5e6
Revises: 4c25e778968d
Create Date: 2026-11-21 11:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = '4c25e778968d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("qa_runs", "qa_issues", "qa_ticker_ledger")


def upgrade() -> None:
    op.create_table('qa_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('target', sa.String(length=200), nullable=False),
    sa.Column('env', sa.String(length=20), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('tickers', sa.JSON(), nullable=False),
    sa.Column('requests', sa.Integer(), nullable=False),
    sa.Column('checks', sa.Integer(), nullable=False),
    sa.Column('issues_new', sa.Integer(), nullable=False),
    sa.Column('issues_seen', sa.Integer(), nullable=False),
    sa.Column('summary', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_qa_runs_started_at'), 'qa_runs', ['started_at'], unique=False)
    op.create_index(op.f('ix_qa_runs_status'), 'qa_runs', ['status'], unique=False)
    op.create_table('qa_issues',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('fingerprint', sa.String(length=40), nullable=False),
    sa.Column('issue_type', sa.String(length=40), nullable=False),
    sa.Column('category', sa.String(length=20), nullable=False),
    sa.Column('severity', sa.String(length=10), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('flow', sa.String(length=40), nullable=False),
    sa.Column('endpoint', sa.String(length=200), nullable=False),
    sa.Column('strategy', sa.String(length=40), nullable=True),
    sa.Column('step', sa.String(length=80), nullable=True),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('expected', sa.Text(), nullable=False),
    sa.Column('actual', sa.Text(), nullable=False),
    sa.Column('tickers', sa.JSON(), nullable=False),
    sa.Column('trace', sa.JSON(), nullable=True),
    sa.Column('context', sa.JSON(), nullable=True),
    sa.Column('occurrences', sa.Integer(), nullable=False),
    sa.Column('first_run_id', sa.Integer(), nullable=True),
    sa.Column('last_run_id', sa.Integer(), nullable=True),
    sa.Column('first_seen', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_seen', sa.DateTime(timezone=True), nullable=False),
    sa.Column('triage', sa.JSON(), nullable=True),
    sa.Column('fix_ref', sa.String(length=300), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_qa_issues_category'), 'qa_issues', ['category'], unique=False)
    op.create_index(op.f('ix_qa_issues_fingerprint'), 'qa_issues', ['fingerprint'], unique=True)
    op.create_index(op.f('ix_qa_issues_last_seen'), 'qa_issues', ['last_seen'], unique=False)
    op.create_index(op.f('ix_qa_issues_severity'), 'qa_issues', ['severity'], unique=False)
    op.create_index(op.f('ix_qa_issues_status'), 'qa_issues', ['status'], unique=False)
    op.create_table('qa_ticker_ledger',
    sa.Column('symbol', sa.String(length=24), nullable=False),
    sa.Column('runs', sa.Integer(), nullable=False),
    sa.Column('last_tested_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_cohort', sa.String(length=30), nullable=True),
    sa.Column('last_result', sa.String(length=12), nullable=True),
    sa.PrimaryKeyConstraint('symbol')
    )
    op.create_index(op.f('ix_qa_ticker_ledger_last_tested_at'), 'qa_ticker_ledger', ['last_tested_at'], unique=False)
    if op.get_bind().dialect.name == "postgresql":
        for t in TABLES:
            op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_index(op.f('ix_qa_ticker_ledger_last_tested_at'), table_name='qa_ticker_ledger')
    op.drop_table('qa_ticker_ledger')
    for ix in ("status", "severity", "last_seen", "fingerprint", "category"):
        op.drop_index(op.f(f'ix_qa_issues_{ix}'), table_name='qa_issues')
    op.drop_table('qa_issues')
    op.drop_index(op.f('ix_qa_runs_status'), table_name='qa_runs')
    op.drop_index(op.f('ix_qa_runs_started_at'), table_name='qa_runs')
    op.drop_table('qa_runs')
