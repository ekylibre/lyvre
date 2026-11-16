"""inventaire (lot CG3.d) : stock à rotation lente (blocage 72 B bis, option globale)

Revision ID: b4c6d8e0f2a4
Revises: a3b5c7d9e1f3
Create Date: 2026-11-08 00:30:00.000000

Les lignes déjà bloquées (méthode fiscale « frozen ») sont marquées à rotation lente pour garder leur blocage : l'option
devient globale et ne s'applique plus qu'aux stocks dont la rotation dépasse un an.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b4c6d8e0f2a4'
down_revision = 'a3b5c7d9e1f3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('stock_lines') as batch:
        batch.add_column(sa.Column('slow_rotation', sa.Boolean(), nullable=True))
    op.execute("UPDATE stock_lines SET slow_rotation = 1 WHERE fiscal_method = 'frozen'")


def downgrade():
    with op.batch_alter_table('stock_lines') as batch:
        batch.drop_column('slow_rotation')
