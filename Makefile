# Vérification locale complète (pas de CI : le build de production est fait
# par Dokploy à partir du Dockerfile).
.PHONY: check front-install front-check front-build test e2e dev-front docker-build captures site-install site site-dev site-check

PYTHON ?= .venv/bin/python
NPM ?= npm --prefix frontend
SITE_NPM ?= npm --prefix site

check: front-check test site-check

front-install:
	$(NPM) ci --no-audit --no-fund

front-check: front-install
	$(NPM) run typecheck
	$(NPM) test
	$(NPM) run build

test:
	$(PYTHON) -m pytest -q

# Parcours de bout en bout (Playwright) sur base jetable : scripts/e2e_server.py.
# Première fois : npx --prefix frontend playwright install chromium
e2e: front-install
	$(NPM) run build
	$(NPM) run e2e

# Serveur Vite (HMR) : lancer Flask avec VITE_DEV_SERVER=http://localhost:5173
dev-front:
	$(NPM) run dev

docker-build:
	docker compose build

# ---------------------------------------------------------------- site lyvre.org (site/, doc/site.md)
site-install:
	$(SITE_NPM) ci --no-audit --no-fund

# Construction : relit data/changelog.yml, data/features.yml et doc/images (site/scripts/prebuild.mjs).
site: site-install
	$(SITE_NPM) run build

site-dev: site-install
	$(SITE_NPM) run dev

# Types, construction, parcours et accessibilité (Playwright + axe).
# Première fois : npx --prefix site playwright install chromium
site-check: site
	$(SITE_NPM) run typecheck
	$(SITE_NPM) run e2e

# Captures du README et du site (doc/images/) sur une base jetable aux données fabriquées : serveur neuf,
# captures, arrêt du serveur. Pas à chaque commit : quand l'interface change.
captures: front-install
	$(NPM) run build
	@$(PYTHON) scripts/e2e_server.py --demo > /tmp/lyvre-captures-server.log 2>&1 & server=$$!; \
	for i in $$(seq 1 60); do curl -fsS -o /dev/null http://127.0.0.1:5099/login && break; sleep 1; done; \
	(cd frontend && node --input-type=module - ../doc/images < ../scripts/readme_screenshots.mjs); status=$$?; \
	kill $$server; exit $$status
