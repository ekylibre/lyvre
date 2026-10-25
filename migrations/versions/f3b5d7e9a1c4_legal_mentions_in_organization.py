"""lot G2 : mentions légales dans Structure (reprises de Facturation), NAF, SIREN des tiers

Revision ID: f3b5d7e9a1c4
Revises: e2a4c6e8f0b3
Create Date: 2026-10-25 21:00:00.000000

Facturation → Structure, champ par champ : Structure vide → valeur copiée ; les deux remplies et
différentes → Structure garde la sienne, et l'écart est écrit dans la sortie (journaux de
déploiement). Le RCS libre de Facturation (« RCS Saintes 840 968 499 ») donne le greffe.
"""
import re

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f3b5d7e9a1c4'
down_revision = 'e2a4c6e8f0b3'
branch_labels = None
depends_on = None

RCS_PATTERN = re.compile(r"RCS\s+(.+?)(?:\s+[AB])?(?:\s+\d[\d\s]*)?$", re.IGNORECASE)


def rcs_city(text):
    """Greffe lu dans une mention RCS libre, ou None."""
    match = RCS_PATTERN.search((text or "").strip())
    city = re.sub(r"^(?:de\s+|d['’])", "", match.group(1).strip(" ,-—")) if match else ""
    return city or None


def _warn(message):
    print(f"[G2] {message}")


def upgrade():
    with op.batch_alter_table('organization') as batch:
        batch.add_column(sa.Column('share_capital_cents', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('vat_number', sa.String(length=20), nullable=True))
        batch.add_column(sa.Column('naf_code', sa.String(length=8), nullable=True))
        batch.add_column(sa.Column('naf_nomenclature', sa.String(length=12), nullable=True))
    with op.batch_alter_table('entities') as batch:
        batch.add_column(sa.Column('siren', sa.String(length=9), nullable=True))
        batch.add_column(sa.Column('naf_code', sa.String(length=8), nullable=True))
        batch.add_column(sa.Column('naf_nomenclature', sa.String(length=12), nullable=True))
        batch.create_index('ix_entities_siren', ['siren'])

    bind = op.get_bind()
    settings = bind.execute(sa.text(
        "SELECT legal_form, share_capital_cents, rcs, vat_number FROM billing_settings ORDER BY id LIMIT 1")).first()
    org = bind.execute(sa.text(
        "SELECT id, legal_form, share_capital_cents, rcs_city, vat_number FROM organization ORDER BY id LIMIT 1")).first()
    if settings is not None and org is not None:
        vat = (settings.vat_number or "").replace(" ", "").upper() or None
        city = rcs_city(settings.rcs)
        if settings.rcs and city is None:
            _warn(f"RCS « {settings.rcs} » illisible : greffe à saisir dans Structure.")
        values = {}
        for column, label, current, incoming in (
                ("legal_form", "forme juridique", org.legal_form, settings.legal_form),
                ("share_capital_cents", "capital (centimes)", org.share_capital_cents, settings.share_capital_cents),
                ("rcs_city", "greffe du RCS", org.rcs_city, city),
                ("vat_number", "TVA intracommunautaire", org.vat_number, vat)):
            if incoming in (None, ""):
                continue
            if current in (None, ""):
                values[column] = incoming
            elif str(current).strip().lower() != str(incoming).strip().lower():
                _warn(f"{label} : Structure « {current} » conservée, Facturation « {incoming} » ignorée.")
        if values:
            assignments = ", ".join(f"{column} = :{column}" for column in values)
            bind.execute(sa.text(f"UPDATE organization SET {assignments} WHERE id = :id"), {**values, "id": org.id})
            _warn("repris de Facturation : " + ", ".join(sorted(values)) + ".")
    elif settings is not None and any((settings.legal_form, settings.share_capital_cents, settings.rcs,
                                       settings.vat_number)):
        _warn("mentions de Facturation non reprises : aucune Structure renseignée.")

    bind.execute(sa.text(
        "UPDATE entities SET siren = substr(siret, 1, 9) "
        "WHERE siret IS NOT NULL AND length(siret) IN (9, 14) AND siret NOT GLOB '*[^0-9]*'"))  # 9 : clients Qonto

    with op.batch_alter_table('billing_settings') as batch:
        batch.drop_column('legal_form')
        batch.drop_column('share_capital_cents')
        batch.drop_column('rcs')
        batch.drop_column('vat_number')


def downgrade():
    with op.batch_alter_table('billing_settings') as batch:
        batch.add_column(sa.Column('legal_form', sa.String(length=100), nullable=True))
        batch.add_column(sa.Column('share_capital_cents', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('rcs', sa.String(length=100), nullable=True))
        batch.add_column(sa.Column('vat_number', sa.String(length=20), nullable=True))
    bind = op.get_bind()
    org = bind.execute(sa.text(
        "SELECT legal_form, share_capital_cents, rcs_city, siren, vat_number FROM organization ORDER BY id LIMIT 1")).first()
    if org is not None:
        rcs = None
        if org.rcs_city:
            siren = org.siren or ""
            rcs = f"RCS {org.rcs_city}" + (f" {siren[:3]} {siren[3:6]} {siren[6:]}" if len(siren) == 9 else "")
        bind.execute(sa.text(
            "UPDATE billing_settings SET legal_form = :legal_form, share_capital_cents = :capital, rcs = :rcs, "
            "vat_number = :vat"), {"legal_form": org.legal_form, "capital": org.share_capital_cents, "rcs": rcs,
                                   "vat": org.vat_number})
    with op.batch_alter_table('entities') as batch:
        batch.drop_index('ix_entities_siren')
        batch.drop_column('naf_nomenclature')
        batch.drop_column('naf_code')
        batch.drop_column('siren')
    with op.batch_alter_table('organization') as batch:
        batch.drop_column('naf_nomenclature')
        batch.drop_column('naf_code')
        batch.drop_column('vat_number')
        batch.drop_column('share_capital_cents')
