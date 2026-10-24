# Signature électronique des baux : serveur Documenso

Lyvre envoie les baux à la signature par l'API de **Documenso** (édition communautaire, licence
AGPL, auto-hébergée ; l'édition libre de Docuseal ne permet pas d'envoyer un PDF par l'API). Chaque
instance de Lyvre renseigne **son** serveur et **son** jeton dans Configuration › Intégrations ›
Documenso ; plusieurs instances peuvent viser le même serveur.

Fichiers (Documenso v2.20.0 + PostgreSQL 15) :

- **Dokploy** (serveur seconde-nature-kvm) : `docker/documenso/compose.dokploy.yml`, réglages
  `docker/documenso/dokploy.env.example` — procédure ci-dessous ;
- **sans Dokploy** (docker compose seul, derrière un proxy) : `docker/documenso/compose.yml`,
  `docker/documenso/env.example` — voir « Mise en place sans Dokploy ».

## Déploiement Dokploy (seconde-nature-kvm)

Adresse retenue dans les exemples : `https://signature.seconde-nature.net` (à adapter).

### 1. DNS

Chez le fournisseur DNS de `seconde-nature.net` : enregistrement **A** `signature` → adresse IP
publique de seconde-nature-kvm (la même que celle de `compta.seconde-nature.net`). Vérifier :
`dig +short signature.seconde-nature.net`.

### 2. Secrets et certificat (sur un poste, pas dans le dépôt)

```sh
mkdir -p ~/documenso-secrets && cd ~/documenso-secrets && umask 077
for v in POSTGRES_PASSWORD NEXTAUTH_SECRET NEXT_PRIVATE_ENCRYPTION_KEY NEXT_PRIVATE_ENCRYPTION_SECONDARY_KEY; do
  echo "$v=$(openssl rand -hex 32)"; done > secrets.env
P=$(openssl rand -hex 16); echo "NEXT_PRIVATE_SIGNING_PASSPHRASE=$P" >> secrets.env
openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes -keyout key.pem -out cert.pem \
  -subj "/CN=Signature des baux Seconde Nature"
openssl pkcs12 -export -out cert.p12 -inkey key.pem -in cert.pem -passout pass:$P && rm key.pem
echo "NEXT_PRIVATE_SIGNING_LOCAL_FILE_CONTENTS=$(base64 -w0 cert.p12)" >> secrets.env
```

Garder `cert.p12` et `secrets.env` en lieu sûr (gestionnaire de mots de passe) : sans le certificat,
les PDF déjà signés restent valides mais on ne peut pas en signer de nouveaux avec la même identité.

### 3. Service Compose dans Dokploy

1. Dokploy de seconde-nature-kvm › **Projects** › projet *Seconde Nature* (ou un projet
   *Signature*) › **Create Service** › **Compose** ; nom `documenso` ; type **Docker Compose**.
2. Onglet **General** › *Provider* : **Raw** ; coller le contenu de
   `docker/documenso/compose.dokploy.yml` ; **Save**.
   (Variante Git : dépôt de Lyvre, *Compose Path* `./docker/documenso/compose.dokploy.yml`, sans
   *Autodeploy* : Documenso n'a pas à être redéployé à chaque poussée de Lyvre.)
3. Onglet **Environment** : coller `docker/documenso/dokploy.env.example`, puis remplacer les lignes
   vides par celles de `secrets.env` et renseigner :
   - `NEXT_PUBLIC_WEBAPP_URL=https://signature.seconde-nature.net` ;
   - le **SMTP** (le même que celui qui envoie les e-mails de Seconde Nature, ou un compte dédié) :
     hôte, port (587 + `NEXT_PRIVATE_SMTP_SECURE=false` en STARTTLS ; 465 + `true` en TLS), identifiant,
     mot de passe, `NEXT_PRIVATE_SMTP_FROM_ADDRESS` (adresse autorisée par ce SMTP) ;
   - `NEXT_PUBLIC_DISABLE_SIGNUP=false` pour l'instant.

   **Save**.
4. Onglet **Domains** › **Add Domain** : *Service* `documenso`, *Host*
   `signature.seconde-nature.net`, *Path* `/`, *Container Port* `3500`, **HTTPS** activé,
   *Certificate* **Let's Encrypt** ; **Create**. (**Preview Compose** montre les labels Traefik et le
   réseau `dokploy-network` que Dokploy ajoute au service.)
5. **Deploy**. Onglet **Logs** (service `documenso`) : `Telemetry is disabled`, puis le serveur
   démarré ; ouvrir `https://signature.seconde-nature.net` (certificat Let's Encrypt après quelques
   secondes).

### 4. Compte, inscriptions fermées, jeton

1. Sur `https://signature.seconde-nature.net` : **Sign up** avec l'adresse de l'administrateur,
   confirmer l'e-mail (vérifie au passage le SMTP).
2. Créer l'**équipe** (ex. « Seconde Nature »).
3. Dokploy › Environment : `NEXT_PUBLIC_DISABLE_SIGNUP=true` › **Save** › **Deploy** (plus personne
   ne peut créer de compte ; les signataires n'en ont pas besoin).
4. Documenso › **Paramètres de l'équipe** › **Jetons d'API** › créer un jeton **sans expiration** ;
   le copier (`api_…`, affiché une seule fois).

### 5. Lyvre

Dans l'instance concernée (ex. SCI Chênes Verts) : Configuration › Intégrations › **Documenso** :
**Activer**, URL `https://signature.seconde-nature.net`, jeton, **Enregistrer et tester** (« Serveur
Documenso … accessible, jeton d'API accepté »). Puis, sur un bail validé, un premier envoi à la
signature **vers vos propres adresses** (gérants et preneur de test) pour contrôler e-mails,
paraphes et PDF signé avant le premier vrai bail.

> Production de Lyvre : le module de baux (lots L1 à L4) et ses migrations seront déployés avec la
> migration de production (`compta.seconde-nature.net`) ; le serveur Documenso peut être monté avant.

### 6. Sauvegardes et mises à jour

- **Base** : volume nommé `documenso-database` ; Dokploy › service › **Volume Backups** (vers une
  destination S3 configurée dans Dokploy), ou à la main :
  `docker exec <conteneur database> pg_dump -U documenso documenso > documenso.sql`.
  Les PDF signés et journaux d'audit sont aussi conservés par Lyvre avec chaque bail.
- **Mise à jour** : changer la version de l'image `documenso/documenso` dans le compose (version
  publiée depuis au moins deux semaines ; relire `packages/ee/FEATURES` du dépôt Documenso),
  **Save** › **Deploy**.
- **Ancien serveur Docuseal** (`docuseal.seconde-nature.net`) : inutile pour Lyvre (son édition libre
  n'accepte pas de PDF par l'API) ; à arrêter quand vous le souhaitez.

## Mise en place sans Dokploy

1. **Dossier** sur le serveur (par exemple `/opt/documenso`) : y copier `compose.yml` et
   `env.example` → `.env` (`chmod 600 .env`), remplir les secrets (`openssl rand -hex 32` pour
   chacun), l'adresse publique et le SMTP.
2. **Certificat de signature** (`cert.p12`, dans le même dossier) : un certificat auto-signé suffit
   (signature électronique simple) ; les PDF signés portent une signature numérique valide, signalée
   « émetteur non approuvé » par les lecteurs tant que le certificat n'est pas reconnu.

   ```sh
   openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes -keyout key.pem -out cert.pem \
     -subj "/CN=Signature des baux"
   openssl pkcs12 -export -out cert.p12 -inkey key.pem -in cert.pem   # mot de passe → NEXT_PRIVATE_SIGNING_PASSPHRASE
   rm key.pem && chmod 640 cert.p12
   ```

3. **Démarrer** : `docker compose up -d` ; Documenso écoute sur `127.0.0.1:3500`.
4. **Proxy HTTPS** (nginx, Caddy…) de `https://signature.seconde-nature.net` vers
   `127.0.0.1:3500` (adresse = `NEXT_PUBLIC_WEBAPP_URL`).
5. **Compte** : s'inscrire sur l'adresse publique, confirmer l'e-mail, créer l'équipe ; puis
   `NEXT_PUBLIC_DISABLE_SIGNUP=true` dans `.env` et `docker compose up -d` (plus d'inscription libre).
6. **Jeton** : Documenso › Paramètres de l'équipe › Jetons d'API › créer (sans expiration) ; le
   copier (`api_…`, affiché une seule fois).
7. **Lyvre** : Configuration › Intégrations › **Documenso** : activer, URL
   `https://signature.seconde-nature.net`, jeton, **Enregistrer et tester**.

## Ce que fait Lyvre à l'envoi

1. PDF du bail figé avec, dans chaque case du bloc de signatures, la balise `{{signature, rN}}`
   (N = rang de signature : gérants dans l'ordre du registre, puis preneur), en blanc ;
2. création de l'envoi (brouillon), signataires dans l'ordre (signature **séquentielle**) ;
3. champs de signature agrandis (32 % × 7 % de la page) ; si une balise n'est pas trouvée, l'envoi
   est supprimé et une erreur s'affiche ;
4. une case de **paraphe** par signataire en bas à droite de **chaque page**, dans la bande entre la
   fin du texte et le pied de page (le paraphe s'inscrit d'un clic : initiales du signataire) ;
5. distribution : Documenso invite le premier signataire, puis le suivant quand le précédent a signé.

Suivi depuis la fiche du bail (à l'ouverture, au plus une fois par minute, ou « Actualiser ») ;
signé : le PDF signé (avec la page « Certificat de signature » de Documenso) et le journal d'audit
sont rangés avec le bail.

## Sauvegardes

Base PostgreSQL (volume `documenso_database`) : `docker compose exec database pg_dump -U documenso
documenso > documenso.sql`. Les PDF signés sont aussi conservés par Lyvre avec chaque bail.

## Mise à jour

Changer la version de l'image dans `compose.yml` (version publiée depuis au moins deux semaines),
`docker compose pull && docker compose up -d`. Relire les fonctions réservées à l'édition
entreprise (`packages/ee/FEATURES` du dépôt Documenso) avant de monter de version.
