# Échéancier des exploitations : résumé du lundi

Lots AG9a.c et AG9a.d (conception : `claudedocs/design_echeancier_agricole.md` § 6 et § 7). Pour les instances au
plan « Exploitation agricole », **Compta › Échéancier** liste les déclarations, paiements et démarches. Chaque
lundi, un résumé part par e-mail aux utilisateurs abonnés.

## Ce que contient le résumé

Il reprend quatre blocs, calculés pour la semaine du lundi :

- **En retard** : échéances passées et non faites, avec les pénalités indiquées dans leur fiche ;
- **Cette semaine** : de J à J+7, avec le montant calculé par Lyvre et le lien vers l'écran qui prépare la déclaration ;
- **À préparer** : de J+8 à J+45, avec ce qui manque (déclaration à préparer dans Lyvre, montant à valider, date à
  confirmer) ;
- **À vérifier** : les détections de l'échéancier (changement de régime, crédit de TVA, option à dénoncer,
  relevés non rapprochés…).

Avant le calcul, les prélèvements reconnus sur les relevés sont rattachés aux échéances payées (voir le § 6.1 de la
conception).

Une instance sans rien à signaler ne reçoit pas d'e-mail. Elle reçoit quand même la notification de la semaine
dans l'application. Le tableau de bord d'une exploitation montre le même résumé en tête.

## Destinataires

| Utilisateur | Reçoit le résumé |
|---|---|
| Administrateur ou trésorier de l'instance | oui, par défaut ; il peut se désabonner |
| Expert-comptable (lecture seule) | non |
| Administrateur global sans rôle sur l'instance | seulement s'il s'abonne depuis l'échéancier |

L'abonnement se règle dans **Compta › Échéancier** (« Résumé du lundi par e-mail »), instance par instance. Chaque
e-mail porte aussi un lien de désabonnement signé, qui demande une confirmation : un aperçu automatique du lien par
la messagerie ne désabonne pas.

## Configuration

Le résumé passe par le **SMTP du serveur**, le même que pour le lien « Mot de passe oublié ». Ce n'est pas
l'intégration SMTP de chaque instance. On le règle sur le relais SMTP de Brevo :

```
MAIL_SERVER=smtp-relay.brevo.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=<identifiant SMTP du compte Brevo>
MAIL_PASSWORD=<clé SMTP Brevo>
MAIL_DEFAULT_SENDER=Lyvre <no-reply@votre-domaine>
APP_BASE_URL=https://compta.example.org
```

L'adresse d'expédition doit appartenir à un domaine authentifié dans Brevo (SPF, DKIM). Sans `APP_BASE_URL`, la
commande s'arrête, car les liens de l'e-mail ne peuvent pas être construits.

## Commande

```
flask agenda send-weekly                      # aujourd'hui
flask agenda send-weekly --date 2026-11-02    # semaine d'un jour donné
flask agenda send-weekly --dry-run            # liste les envois sans rien envoyer ni enregistrer
```

La commande parcourt les instances agricoles actives et écrit une ligne par destinataire :
`agenda weekly 2026-W45 <instance> user=<id> envoyé | déjà envoyé | rien à signaler | échec : …`. Elle se termine
par un bilan.

- **Idempotente** : au plus un envoi par utilisateur et par semaine ISO (`agenda_subscriptions.last_sent_week`). La
  relancer le même jour, ou plus tard dans la semaine, n'envoie rien en double. La notification dans l'application
  n'est créée qu'une fois par semaine.
- **Échecs** : un envoi qui échoue n'est pas noté comme fait. La relance suivante le retente. La commande sort avec
  le code 1 s'il y a eu un échec, ce qui le rend visible dans `systemctl status` ou dans le courrier de cron.

## Planification

Lyvre n'a pas de planificateur : c'est le serveur qui lance la commande chaque lundi à 7 h.

### Avec Docker et un timer systemd (recommandé)

`/etc/systemd/system/lyvre-agenda.service` :

```ini
[Unit]
Description=Lyvre : résumé du lundi de l'échéancier
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
WorkingDirectory=/srv/lyvre
ExecStart=/usr/bin/docker compose exec -T web flask agenda send-weekly
```

`/etc/systemd/system/lyvre-agenda.timer` :

```ini
[Unit]
Description=Lyvre : résumé de l'échéancier chaque lundi à 7 h

[Timer]
OnCalendar=Mon *-*-* 07:00:00 Europe/Paris
Persistent=true

[Install]
WantedBy=timers.target
```

```
systemctl daemon-reload
systemctl enable --now lyvre-agenda.timer
systemctl list-timers lyvre-agenda.timer       # prochain passage
journalctl -u lyvre-agenda.service             # lignes d'envoi
```

`Persistent=true` lance la commande au redémarrage si le serveur était éteint le lundi à 7 h. L'idempotence
empêche les envois en double. Adapter `WorkingDirectory` au dossier du `docker-compose.yml`.

### Avec cron

```
0 7 * * 1  cd /srv/lyvre && docker compose exec -T web flask agenda send-weekly >> /var/log/lyvre-agenda.log 2>&1
```

Sans Docker, remplacer `docker compose exec -T web` par l'environnement virtuel de l'application :
`cd /srv/lyvre && FLASK_APP=run.py .venv/bin/flask agenda send-weekly`.

## Base de données

Le lot ajoute la table `agenda_subscriptions` (migration `c9d1f3b5e7a8`) dans la base de chaque instance. Elle
contient une ligne par utilisateur ayant changé son abonnement ou reçu un résumé, avec la semaine du dernier
envoi. La colonne `ical_token` porte le jeton de l'adresse iCal.

## Calendrier iCal

Chaque utilisateur peut créer une adresse secrète depuis **Compta › Échéancier › Agenda (iCal)** :
`<APP_BASE_URL>/agenda/ical/<instance>/<jeton>.ics`. On la colle dans un logiciel d'agenda comme abonnement. Elle
donne les échéances des 30 derniers jours et des 400 suivants, sans connexion.

- Le jeton est aléatoire (256 bits). Le **régénérer** coupe l'ancienne adresse, le **révoquer** la supprime.
- L'adresse cesse de marcher dès que l'utilisateur est désactivé ou perd son rôle sur l'instance.
- La lecture du calendrier n'écrit rien en base : les paiements sont rattachés à l'ouverture de l'échéancier et
  par le résumé du lundi.
- Les logiciels d'agenda relisent l'adresse à leur rythme (Google Agenda : plusieurs heures). Le fichier suggère
  12 h (`REFRESH-INTERVAL`).
