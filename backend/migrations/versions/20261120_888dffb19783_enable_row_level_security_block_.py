"""enable row level security (block Supabase Data API access)

Revision ID: 888dffb19783
Revises: 5cbb2a4c1dbc
Create Date: 2026-11-20 16:52:39.608480

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '888dffb19783'
down_revision: Union[str, Sequence[str], None] = '5cbb2a4c1dbc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_LOOP = """
DO $$
DECLARE t record;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = current_schema() LOOP
    EXECUTE 'ALTER TABLE ' || quote_ident(t.tablename) || ' {action} ROW LEVEL SECURITY';
  END LOOP;
END $$;
"""


def upgrade() -> None:
    """Enable RLS on every table. With no policies, PostgREST roles (anon/authenticated on Supabase) can't
    read or write anything; the API connects as the table owner, which RLS does not restrict."""
    if op.get_context().dialect.name == "postgresql":
        op.execute(_LOOP.format(action="ENABLE"))


def downgrade() -> None:
    if op.get_context().dialect.name == "postgresql":
        op.execute(_LOOP.format(action="DISABLE"))
