# Vérification locale complète (pas de CI : le build de production est fait
# par Dokploy à partir du Dockerfile).
.PHONY: check front-install front-check front-build test e2e dev-front docker-build

PYTHON ?= .venv/bin/python
NPM ?= npm --prefix frontend

check: front-check test

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
