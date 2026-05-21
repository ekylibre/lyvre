FROM python:3.12-slim-bookworm

# Minimal runtime tools (curl is used by the healthcheck).
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
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
