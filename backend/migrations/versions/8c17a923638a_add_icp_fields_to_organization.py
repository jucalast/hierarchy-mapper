"""add icp fields to organization

Revision ID: 8c17a923638a
Revises: 
Create Date: 2026-05-05 11:15:53.545447

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c17a923638a'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Adiciona colunas de ICP
    op.add_column('organizations', sa.Column('icp_score', sa.Integer(), nullable=True))
    op.add_column('organizations', sa.Column('icp_tier', sa.String(), nullable=True))
    
    # Adiciona índices se não existirem (SQLite ignora se já existirem dependendo da versão, mas alembic tenta criar)
    # Para ser seguro em SQLite, vamos focar apenas no que é novo.
    try:
        op.create_index(op.f('ix_organizations_icp_score'), 'organizations', ['icp_score'], unique=False)
    except: pass
    try:
        op.create_index(op.f('ix_organizations_icp_tier'), 'organizations', ['icp_tier'], unique=False)
    except: pass


def downgrade() -> None:
    op.drop_index(op.f('ix_organizations_icp_tier'), table_name='organizations')
    op.drop_index(op.f('ix_organizations_icp_score'), table_name='organizations')
    op.drop_column('organizations', 'icp_tier')
    op.drop_column('organizations', 'icp_score')
