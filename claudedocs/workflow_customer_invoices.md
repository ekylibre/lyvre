# Workflow — Factures clients Odoo (`customer-invoices`)

> Plan d'implémentation pour ajouter la synchronisation des factures clients Odoo
> (`account.move` avec `move_type='out_invoice'`), en miroir strict du module
> **Commandes POS** (`app/services/odoo_pos_sync.py` + blueprint `orders`).
>
> **Périmètre — ne fait PAS partie de ce plan** : exécution du code, génération
> d'écritures comptables automatiques à partir des factures. Le module est
> uniquement *read-only sync + visualisation + statut*, comme `orders`.

---

## 1. Analyse de l'existant — pourquoi ce mirror

Le module **Commandes POS** est le patron à copier :

| Couche | Fichier source | Rôle |
|--------|---------------|------|
| Modèle parent | `app/models/order.py` | `Order` (table `orders`) — upsert par `odoo_id`, FK `entity_id` |
| Modèle ligne | `app/models/order_line.py` | `OrderLine` — FK `order_id` CASCADE |
| Modèle paiement | `app/models/order_payment.py` | `OrderPayment` — FK `order_id` CASCADE |
| Client RPC | `app/services/odoo_client.py` | `OdooClient.search_read()` — réutilisable tel quel |
| Sync service | `app/services/odoo_pos_sync.py` | `sync_pos_orders()` — pagination, upsert, rattachement Entity par email |
| Resolver Entity | `app/services/entity_resolver.py` | `entity_by_email()` + `unique_entity_name()` — réutilisable |
| Blueprint | `app/views/orders.py` | 3 routes : `index`, `detail`, `sync` |
| Templates | `app/templates/orders/{index,detail}.html` | Liste + fiche |
| Nav | `app/templates/base.html:51-53` | Entrée principale `Commandes POS` |

Côté Odoo, **`account.move`** (modèle des factures) est nettement plus riche
qu'un `pos.order` : double notion d'état (`state` comptable + `payment_state`),
échéances, multi-paiements via réconciliation. Le mirror reste fidèle au patron
POS mais étoffe les champs status.

---

## 2. Modèle de données cible Odoo

Domaine principal :

```python
domain = [("move_type", "=", "out_invoice")]
```

> Pour gérer les avoirs clients plus tard, élargir à `("move_type", "in", ["out_invoice", "out_refund"])` — **hors périmètre** de ce plan.

**Champs Odoo `account.move` à récupérer :**

| Champ Odoo | Type | Usage côté compta-asso |
|------------|------|------------------------|
| `id` | int | `odoo_id` (clé d'idempotence) |
| `name` | str | numéro de facture, ex `INV/2026/00042` |
| `ref` | str | référence interne libre |
| `move_type` | str | toujours `out_invoice` (filtre déjà appliqué) |
| `state` | str | `draft`, `posted`, `cancel` |
| `payment_state` | str | `not_paid`, `in_payment`, `paid`, `partial`, `reversed`, `invoicing_legacy` |
| `partner_id` | m2o | id du client (`res.partner`) |
| `invoice_date` | date | date d'émission |
| `invoice_date_due` | date | échéance |
| `currency_id` | m2o | code devise |
| `amount_untaxed` | float | total HT |
| `amount_tax` | float | total TVA |
| `amount_total` | float | total TTC |
| `amount_residual` | float | reste à payer |
| `invoice_origin` | str | origine (ex : commande source) |
| `journal_id` | m2o | journal de ventes |
| `team_id` | m2o | équipe commerciale (utile pour filtres futurs) |
| `invoice_line_ids` | o2m | IDs des lignes à récupérer ensuite |
| `narration` | text | message bas de facture |

**Champs `account.move.line` (lignes de facture) :**

Filtrer côté Odoo sur les lignes "produit" uniquement — les lignes de TVA et de
contrepartie comptable polluent les résultats. Le filtre fiable est :
`display_type == 'product'` (Odoo ≥ 16) **OU** `product_id != False` (fallback
compatible Odoo 14/15).

| Champ Odoo | Usage |
|------------|-------|
| `id` | `odoo_id` |
| `move_id` | FK vers la facture |
| `product_id` | m2o produit |
| `name` | description ligne |
| `quantity` | qté |
| `price_unit` | PU HT |
| `discount` | remise % |
| `price_subtotal` | sous-total HT |
| `price_total` | sous-total TTC |
| `tax_ids` | m2m IDs taxes (stocké en CSV comme `OrderLine.tax_ids`) |
| `account_id` | m2o compte de produit (utile pour analyse future) |

**Paiements (optionnel — phase 2 du plan) :**

Sur `account.move`, le champ `invoice_payments_widget` est un JSON sérialisé
contenant la liste des paiements rapprochés. Plus propre : utiliser
`_get_reconciled_invoices_partials()` n'est pas exposé en RPC ⇒ on récupère
plutôt via `account.payment` filtré par
`reconciled_invoice_ids` ⊃ {invoice.id}, puis on lit le JSON
`invoice_payments_widget` pour avoir les montants partiels.

**Décision plan** : ne **pas** créer de table `customer_invoice_payments` au
premier jet. `payment_state` + `amount_residual_cents` suffisent à afficher le
statut. Une phase 2 pourra rajouter la table si l'utilisateur a besoin du détail
des paiements.

---

## 3. Découpage en phases

### Phase A — Modèles & migration (Alembic)

**A.1** Créer `app/models/customer_invoice.py` — classe `CustomerInvoice`,
table `customer_invoices`.

Colonnes (en miroir de `Order` + spécificités facture) :

| Colonne | Type | Notes |
|---------|------|-------|
| `id` | Integer PK | |
| `odoo_id` | Integer UNIQUE NOT NULL index | clé d'idempotence |
| `name` | String(100) index | numéro facture Odoo |
| `ref` | String(200) | référence libre |
| `state` | String(20) index | `draft` / `posted` / `cancel` |
| `payment_state` | String(20) index | `not_paid` / `in_payment` / `paid` / `partial` / `reversed` |
| `partner_id` | Integer | id Odoo du `res.partner` |
| `partner_name` | String(200) | |
| `partner_email` | String(200) index | rattachement Entity |
| `entity_id` | Integer FK→entities ON DELETE SET NULL index | |
| `invoice_date` | Date index | |
| `invoice_date_due` | Date | |
| `currency` | String(3) NOT NULL default `EUR` | |
| `amount_untaxed_cents` | Integer NOT NULL default 0 | total HT |
| `amount_tax_cents` | Integer NOT NULL default 0 | TVA |
| `amount_total_cents` | Integer NOT NULL default 0 | TTC |
| `amount_residual_cents` | Integer NOT NULL default 0 | reste à payer |
| `invoice_origin` | String(200) | |
| `journal_name` | String(100) | nom du journal de ventes Odoo |
| `narration` | Text | |
| `raw_payload` | Text | JSON brut |
| `created_at` | DateTime default utcnow | |
| `imported_at` | DateTime default utcnow | |

Relations :
- `entity = relationship("Entity", foreign_keys=[entity_id])`
- `lines = relationship("CustomerInvoiceLine", backref="invoice", lazy="dynamic", cascade="all, delete-orphan", passive_deletes=True)`

Constantes en tête de module (en miroir de `POS_ORDER_STATES`) :

```python
CUSTOMER_INVOICE_STATES = [
    ("draft", "Brouillon"),
    ("posted", "Comptabilisée"),
    ("cancel", "Annulée"),
]
CUSTOMER_INVOICE_PAYMENT_STATES = [
    ("not_paid", "Non payée"),
    ("in_payment", "En cours de paiement"),
    ("partial", "Partiellement payée"),
    ("paid", "Payée"),
    ("reversed", "Annulée par avoir"),
    ("invoicing_legacy", "Hérité"),
]
```

**A.2** Créer `app/models/customer_invoice_line.py` — classe
`CustomerInvoiceLine`, table `customer_invoice_lines`.

| Colonne | Type | Notes |
|---------|------|-------|
| `id` | Integer PK | |
| `odoo_id` | Integer UNIQUE NOT NULL index | |
| `invoice_id` | Integer FK→customer_invoices ON DELETE CASCADE index NOT NULL | |
| `product_id` | Integer | |
| `product_name` | String(300) | |
| `description` | String(500) | champ Odoo `name` (souvent verbeux) |
| `qty` | Float NOT NULL default 0 | |
| `price_unit_cents` | Integer NOT NULL default 0 | |
| `discount` | Float NOT NULL default 0 | |
| `price_subtotal_cents` | Integer NOT NULL default 0 | HT |
| `price_total_cents` | Integer NOT NULL default 0 | TTC |
| `tax_ids` | String(200) | CSV des IDs taxes Odoo |
| `account_code` | String(20) | code compte produit Odoo (utile filtre futur) |
| `raw_payload` | Text | |
| `imported_at` | DateTime default utcnow | |

**A.3** Mettre à jour `app/models/__init__.py` : importer
`CustomerInvoice`, `CustomerInvoiceLine`, les ajouter à `__all__`.

**A.4** Générer la migration Alembic :

```bash
source .venv/bin/activate
flask db migrate -m "add customer invoices tables"
```

Vérifier ensuite le fichier généré dans `migrations/versions/` — corriger à la
main si Alembic propose à tort de toucher d'autres tables (cas vu sur ce projet
quand des modifs locales non commitées traînent — cf. `git status`).

**Validation** :
- `flask db upgrade` passe.
- `python -c "from app import create_app; from app.models import CustomerInvoice, CustomerInvoiceLine; print('OK')"` — pas d'erreur d'import circulaire.

---

### Phase B — Service de synchronisation

**B.1** Créer `app/services/odoo_invoice_sync.py` en s'inspirant de
`odoo_pos_sync.py` ligne par ligne. Helpers à **recopier tels quels** depuis
`odoo_pos_sync` (ils ne sont pas exportés dans un module commun — on duplique
volontairement plutôt que de refactorer dans ce plan) :
- `_to_cents`
- `_to_datetime` (renommer `_to_date` car les dates de factures sont des `date`
  Odoo et pas des `datetime` — adapter le `strptime` à `%Y-%m-%d`)
- `_m2o_id`, `_m2o_name`, `_currency_code`
- `_chunked`
- `_fetch_partners` (signature identique à POS)
- `_resolve_partner_entity` (signature identique — **NB** : pas de modification
  de `is_member` ici. Les factures clients n'impliquent pas une qualité
  d'adhérent.)

**Constantes :**

```python
PAGE_SIZE = 200

INVOICE_FIELDS = [
    "id", "name", "ref", "move_type", "state", "payment_state",
    "partner_id", "invoice_date", "invoice_date_due", "currency_id",
    "amount_untaxed", "amount_tax", "amount_total", "amount_residual",
    "invoice_origin", "journal_id", "narration",
    "invoice_line_ids",
]
INVOICE_LINE_FIELDS = [
    "id", "move_id", "product_id", "name",
    "quantity", "price_unit", "discount",
    "price_subtotal", "price_total", "tax_ids",
    "account_id", "display_type",
]
PARTNER_FIELDS = ["id", "name", "email", "phone", "mobile"]

DEFAULT_DOMAIN = [
    ("move_type", "=", "out_invoice"),
]
```

**Fonctions :**

```python
def _upsert_invoice(item):
    """Upsert un account.move dans customer_invoices."""

def _upsert_line(item, invoice):
    """Upsert un account.move.line dans customer_invoice_lines.

    Filtre côté Python (en plus du filtre côté Odoo) :
      - product_id absent ET display_type != 'product' → skip
    """

def sync_customer_invoices(domain=None, limit=None, progress_cb=None):
    """Synchronise les factures clients Odoo.

    Étapes (miroir exact de sync_pos_orders) :
      1. Pagination sur account.move avec DEFAULT_DOMAIN + domain utilisateur,
         offset/limit en boucle. Upsert dans customer_invoices.
      2. Pour chaque batch, db.session.flush() puis search_read account.move.line
         par chunks d'IDs (PAGE_SIZE). Filtrage produit (cf. _upsert_line).
      3. Récupération des res.partner pour tous les partner_id rencontrés.
         _resolve_partner_entity par email : crée Entity(entity_type='CLIENT')
         si nouvelle, sinon récupère l'existante.
      4. Rattachement de invoice.entity_id + invoice.partner_email.
      5. db.session.commit() final.

    Retourne :
      {
        'invoices_imported': int, 'invoices_updated': int, 'invoices_total': int,
        'lines_imported': int, 'lines_updated': int, 'lines_total': int,
        'entities_created': int, 'entities_updated': int,
      }
    """
```

**Note importante** : ne **pas** ajouter de `_refresh_member_flag` ici (les
factures clients ≠ adhésions). C'est la différence métier majeure avec POS.

**B.2** Tests manuels :
- Lancer la sync sans factures en base — `invoices_imported` doit refléter le total.
- Relancer immédiatement — `invoices_updated` doit valoir le total, `imported` = 0.
- Modifier `payment_state` côté Odoo (passage à `paid`), resync — le champ doit basculer en base.
- Vérifier qu'un partner sans email ne crée pas d'Entity orpheline.

---

### Phase C — Blueprint Flask

**C.1** Créer `app/views/customer_invoices.py` — copie quasi-conforme de
`app/views/orders.py` :

```python
bp = Blueprint("customer_invoices", __name__, url_prefix="/customer-invoices")

def _odoo_configured():
    return all(current_app.config.get(k) for k in (
        "ODOO_URL", "ODOO_DB", "ODOO_USERNAME", "ODOO_API_KEY",
    ))

@bp.route("/")
@login_required
def index():
    # Filtres GET optionnels : state, payment_state, q (numéro/partenaire)
    invoices = (
        CustomerInvoice.query
        .order_by(CustomerInvoice.invoice_date.desc().nullslast(),
                  CustomerInvoice.id.desc())
        .limit(500).all()
    )
    return render_template(
        "customer_invoices/index.html",
        invoices=invoices,
        states=dict(CUSTOMER_INVOICE_STATES),
        payment_states=dict(CUSTOMER_INVOICE_PAYMENT_STATES),
        configured=_odoo_configured(),
    )

@bp.route("/<int:invoice_id>")
@login_required
def detail(invoice_id):
    invoice = CustomerInvoice.query.get_or_404(invoice_id)
    lines = (
        CustomerInvoiceLine.query.filter_by(invoice_id=invoice.id)
        .order_by(CustomerInvoiceLine.id).all()
    )
    return render_template(
        "customer_invoices/detail.html",
        invoice=invoice, lines=lines,
        states=dict(CUSTOMER_INVOICE_STATES),
        payment_states=dict(CUSTOMER_INVOICE_PAYMENT_STATES),
    )

@bp.route("/sync", methods=["POST"])
@login_required
def sync():
    try:
        result = sync_customer_invoices()
    except OdooConfigError as e:
        flash(str(e), "warning")
        return redirect(url_for("customer_invoices.index"))
    except Exception as e:
        current_app.logger.exception("Sync factures Odoo échouée")
        flash(f"Erreur de synchronisation : {e}", "danger")
        return redirect(url_for("customer_invoices.index"))

    flash(
        "Synchronisation OK — "
        f"{result['invoices_imported']} nouvelle(s), "
        f"{result['invoices_updated']} mise(s) à jour, "
        f"{result['lines_total']} ligne(s), "
        f"{result.get('entities_created', 0)} tiers créé(s).",
        "success",
    )
    return redirect(url_for("customer_invoices.index"))
```

**C.2** Enregistrer le blueprint dans `app/__init__.py` :

- Ajouter `from .views.customer_invoices import bp as customer_invoices_bp`
  (juste après l'import de `orders_bp`).
- Ajouter `app.register_blueprint(customer_invoices_bp)` (juste après
  `app.register_blueprint(orders_bp)`).

---

### Phase D — Templates Jinja2

**D.1** Créer `app/templates/customer_invoices/` :

**`index.html`** — calqué sur `templates/orders/index.html`, avec deux
colonnes statut (état comptable + état paiement) :

Colonnes du tableau :
1. Date facture
2. Numéro (lien vers détail)
3. Référence
4. Client (lien vers entité si rattachée)
5. Total HT *(right, monospace)*
6. TVA *(right, monospace muted)*
7. Total TTC *(right, monospace)*
8. Reste dû *(right, monospace ; rouge si > 0 et state=posted)*
9. État comptable (badge couleur — `posted`=succès, `draft`=secondary,
   `cancel`=danger)
10. État paiement (badge couleur — `paid`=succès, `partial`=warning,
    `in_payment`=info, `not_paid`=danger si échéance dépassée sinon
    secondary, `reversed`=dark)

Filtres GET (formulaire HTML simple, pas HTMX) : `state`, `payment_state`,
`q`. Ces filtres ne sont **pas** dans le scope strict du mirror POS mais sont
recommandés vu le volume probable (factures > commandes POS sur 5 ans).

**`detail.html`** — calqué sur `templates/orders/detail.html` :

Bloc cartes en haut :
- Carte 1 : Total HT
- Carte 2 : TVA
- Carte 3 : Total TTC
- Carte 4 : Reste dû (rouge si > 0)

Bloc info :
- Numéro / Référence / Origine
- Date facture / Échéance / Journal
- Client (lien Entity si rattaché) / Email
- Badges État comptable + État paiement

Tableau **Lignes** — colonnes : Produit, Description, Qté, PU HT, Remise %,
Sous-total HT, Sous-total TTC.

**D.2** Convention badges (à factoriser éventuellement plus tard dans un macro
Jinja partagé) :

```jinja
{% set st = invoice.state %}
{% if st == 'posted' %}
  <span class="badge bg-success">{{ states.get(st, st) }}</span>
{% elif st == 'cancel' %}
  <span class="badge bg-danger">{{ states.get(st, st) }}</span>
{% else %}
  <span class="badge bg-secondary">{{ states.get(st, st or '—') }}</span>
{% endif %}
```

---

### Phase E — Navigation

**E.1** Modifier `app/templates/base.html` :

L'entrée doit s'intégrer naturellement. Deux options :

**Option recommandée** : ajouter une nouvelle entrée au même niveau que
"Commandes POS" :

```jinja
<li class="nav-item">
  <a class="nav-link {% if request.blueprint == 'orders' %}active{% endif %}"
     href="{{ url_for('orders.index') }}">Commandes POS</a>
</li>
<li class="nav-item">
  <a class="nav-link {% if request.blueprint == 'customer_invoices' %}active{% endif %}"
     href="{{ url_for('customer_invoices.index') }}">Factures clients</a>
</li>
```

**Option alternative** (à éviter si le menu Odoo doit grossir plus tard) :
créer un dropdown "Odoo" regroupant "Commandes POS" + "Factures clients".
Pas retenue dans ce plan — on reste sur le mirror plat.

**E.2** Vérification visuelle :
- `python run.py` → naviguer sur `/` après login.
- Le lien "Factures clients" est cliquable, le statut `active` se déclenche
  bien quand on est sur une page du blueprint.

---

### Phase F — Vue détail Entity : faire apparaître les factures

Le module Entity affiche déjà les commandes POS et HelloAsso d'un tiers (cf.
mémoire projet). Pour la cohérence, **ajouter** un bloc "Factures clients" sur
`app/templates/entities/detail.html` listant les `CustomerInvoice` rattachées
via `entity_id`.

**F.1** Côté vue `entities.detail` (à localiser dans
`app/views/entities.py`) : ajouter dans le contexte
`customer_invoices = CustomerInvoice.query.filter_by(entity_id=entity.id).order_by(...).all()`.

**F.2** Côté template : bloc `<h5>Factures clients</h5>` + tableau condensé
(Numéro, Date, TTC, Reste dû, État, Paiement), affiché uniquement si la liste
n'est pas vide — même convention que pour les commandes POS aujourd'hui.

---

## 4. Dépendances entre phases

```
A (modèles + migration)
   │
   ├──► B (service sync) ──► C (blueprint) ──► D (templates) ──► E (nav)
   │                                                              │
   └──────────────────────────────────────────────────────────────┴──► F (intégration Entity)
```

Phase F dépend de A (le modèle doit exister) et D (style des badges réutilisé)
mais peut être faite en parallèle de E.

**Ordre d'exécution recommandé** : A → B → C → D → E → F.
Phase B testable dès que A est mergée (via shell Python). Phases C/D/E peuvent
itérer ensemble.

---

## 5. Points de vigilance

1. **`git status` actuel** révèle des fichiers HelloAsso non commités
   (`helloasso_*`, `entity_resolver.py`, migrations en cours). Avant `flask db
   migrate`, vérifier qu'Alembic ne va pas mélanger ces migrations avec celle
   des factures. Idéalement, commit/stash de l'existant avant la phase A.

2. **Filtrage des lignes de facture** : `account.move.line` contient lignes
   produit, lignes de taxe et ligne de contrepartie tiers. Le filtre
   `display_type='product'` est fiable sur Odoo ≥ 16. Sur Odoo plus ancien,
   utiliser `product_id != False` ET `account_id` commençant par `70x` ou non
   bilan. Tester sur la base réelle avant de figer le filtre.

3. **Pagination Odoo** : `account.move` est typiquement bien plus volumineux
   que `pos.order` (chaque vente POS confirmée peut générer une facture). Sur
   un premier sync, prévoir 30-60 s. Si l'UI doit rester réactive, **basculer
   plus tard sur le pattern `stancer_async` + `SyncJob`** — pas dans ce plan
   pour rester aligné avec le mirror POS synchrone.

4. **`payment_state` Odoo n'est pas trivial** : la valeur `partial` n'existe
   pas en sortie d'usine sur certaines versions ; selon le module installé, on
   peut voir `in_payment` à la place. Stocker la valeur brute Odoo (string)
   sans validation côté Python est la stratégie la plus robuste.

5. **Devises** : si la base contient des factures non-EUR, vérifier que
   `_currency_code` ne casse pas (mais le filtre déjà appliqué dans la sync POS
   gère bien les `False`).

6. **Suppression côté Odoo** : la sync est purement *upsert*. Une facture
   supprimée côté Odoo restera en base locale. Acceptable au premier jet (cf.
   POS qui a le même comportement). Une commande "purge" est *hors périmètre*.

7. **Test minimal manuel** :
   1. Sync à blanc → vérifier compteur.
   2. Modifier une facture côté Odoo (passage `draft` → `posted`).
   3. Resync → vérifier que `state` bascule en base.
   4. Enregistrer un paiement complet côté Odoo.
   5. Resync → vérifier `payment_state='paid'` et `amount_residual_cents=0`.

---

## 6. Checklist d'acceptation

- [ ] `flask db upgrade` passe sur une base fraîche et sur la base existante.
- [ ] `sync_customer_invoices()` appelable depuis le shell Python sans erreur.
- [ ] `sync_customer_invoices()` est idempotent (2e appel : `imported=0`).
- [ ] Le menu "Factures clients" apparaît dans la nav, est cliquable et marque
      l'item actif quand on est sur le blueprint.
- [ ] `/customer-invoices/` liste les factures avec les deux badges de statut.
- [ ] `/customer-invoices/<id>` affiche les lignes avec totaux corrects (somme
      HT/TVA/TTC cohérente avec les totaux Odoo).
- [ ] Création automatique d'Entity de type `CLIENT` pour les nouveaux
      partenaires (par email). Pas de doublons sur resync.
- [ ] Le bouton "Synchroniser depuis Odoo" est désactivé si `.env` ne contient
      pas les 4 variables `ODOO_*` (parité avec `orders.index`).
- [ ] La fiche `/entities/<id>` montre désormais un bloc "Factures clients"
      pour les tiers rattachés.

---

## 7. Fichiers créés / modifiés

**Créés :**

- `app/models/customer_invoice.py`
- `app/models/customer_invoice_line.py`
- `app/services/odoo_invoice_sync.py`
- `app/views/customer_invoices.py`
- `app/templates/customer_invoices/index.html`
- `app/templates/customer_invoices/detail.html`
- `migrations/versions/<hash>_add_customer_invoices_tables.py`

**Modifiés :**

- `app/models/__init__.py` — exports
- `app/__init__.py` — register blueprint
- `app/templates/base.html` — entrée de menu
- `app/views/entities.py` — contexte vue détail
- `app/templates/entities/detail.html` — bloc factures clients

---

## 8. Étape suivante

> **Ce plan s'arrête à la rédaction**. Pour exécuter :
> `/sc:implement claudedocs/workflow_customer_invoices.md`
>
> Lancer phase par phase (A puis B puis C…) plutôt que tout d'un coup —
> chaque phase contient ses propres critères de validation, et la migration
> Alembic (A.4) est le seul pas réellement irréversible.
