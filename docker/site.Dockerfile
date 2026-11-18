# Site public lyvre.org (site/, doc/site.md). Construit par Dokploy depuis le dépôt à chaque push sur main :
# version, nouveautés et fonctionnalités viennent de data/*.yml, sans historique Git.
# Exclusions propres à cette image : docker/site.Dockerfile.dockerignore (la .dockerignore racine exclut doc/).
FROM node:22-slim AS build
# Polices pour l'image de partage (og.png, rendue par sharp depuis un SVG).
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /repo/site
COPY site/package.json site/package-lock.json ./
RUN npm ci --no-audit --no-fund
WORKDIR /repo
COPY data/changelog.yml data/features.yml data/
COPY doc/images doc/images
COPY frontend/src/assets frontend/src/assets
COPY frontend/src/app/lyvre.css frontend/src/app/lyvre.css
COPY frontend/src/features/about/comparison.ts frontend/src/features/about/competitors.ts frontend/src/features/about/openSourceVendors.ts frontend/src/features/about/
COPY site site
ARG PUBLIC_SITE_URL=https://lyvre.org
ARG PUBLIC_DEMO_URL=https://demo.lyvre.org
ENV PUBLIC_SITE_URL=$PUBLIC_SITE_URL PUBLIC_DEMO_URL=$PUBLIC_DEMO_URL
WORKDIR /repo/site
RUN npm run build

FROM nginx:1.31.2-alpine
COPY docker/site.nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/site/dist /usr/share/nginx/html
EXPOSE 80
