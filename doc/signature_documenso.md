# Signature électronique des baux : serveur Documenso

Lyvre envoie les baux à la signature par l'API de **Documenso** (édition communautaire, licence
AGPL, auto-hébergée ; l'édition libre de Docuseal ne permet pas d'envoyer un PDF par l'API). Chaque
instance de Lyvre renseigne **son** serveur et **son** jeton dans Configuration › Intégrations ›
Documenso ; plusieurs instances peuvent viser le même serveur.

Fichiers : `docker/documenso/compose.yml` (Documenso v2.20.0 + PostgreSQL 15), modèle des
réglages `docker/documenso/env.example`.

## Mise en place

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
4. une case de **paraphe** par signataire en bas à droite de **chaque page** ;
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
