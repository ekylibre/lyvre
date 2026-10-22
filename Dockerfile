# ---------------------------------------------------------------------------
# Étape 1 — build du front React (Vite : SPA + îlots). Node n'est présent que dans cette
# étape : l'image finale ne contient que le résultat (app/static/dist).
# ---------------------------------------------------------------------------
FROM node:22-slim AS front

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Pages de la SPA, partagées avec Flask (importées par src/app/routes.ts).
COPY app/spa_routes.json /build/app/spa_routes.json
# vite.config.ts : outDir = ../app/static/dist → /build/app/static/dist
RUN npm run build

# ---------------------------------------------------------------------------
# Étape 2 — image d'exécution Python
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm

# Runtime tools : curl (healthcheck) + bibliothèques système requises par
# WeasyPrint pour la génération PDF serveur du rapport d'activité (Pango/Cairo/
# GDK-PixBuf) + polices de base + Tesseract (OCR des factures d'achat, français).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      curl \
      libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 \
      libffi8 fonts-dejavu-core \
      tesseract-ocr tesseract-ocr-fra \
 && rm -rf /var/lib/apt/lists/*

# Non-root user; UID/GID overridable at build time to match the host owner of ./instance.
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd -g ${APP_GID} appgrp \
 && useradd -m -u ${APP_UID} -g ${APP_GID} -s /bin/bash appuser

WORKDIR /app

# Install deps first so application changes don't bust the pip cache layer.
COPY --chown=appuser:appgrp requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt gunicorn==23.*

# Copy the rest of the project. .dockerignore excludes secrets, the venv, data state, etc.
COPY --chown=appuser:appgrp . /app
# Front compilé à l'étape 1 (manifest Vite lu par app/frontend.py).
COPY --from=front --chown=appuser:appgrp /build/app/static/dist /app/app/static/dist

# instance/ is a mount point — make sure the empty directory is owned by appuser
# so the entrypoint can write to it before the volume is mounted (helpful when running
# the image without docker-compose).
RUN mkdir -p /app/instance && chown -R appuser:appgrp /app/instance \
 && chmod +x /app/docker/entrypoint.sh

USER appuser

ENV PYTHONUNBUFFERED=1 \
    FLASK_APP=run.py \
    FLASK_ENV=production

EXPOSE 5000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "-w", "1", "-k", "gthread", "--threads", "4", \
     "-b", "0.0.0.0:5000", "--timeout", "120", "app:create_app()"]
