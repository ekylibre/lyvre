// Site public lyvre.org (claudedocs/besoins_site_lyvre_org.md). Statique, français d'abord (structure prête
// pour /en/). Version, nouveautés et fonctionnalités viennent de data/changelog.yml et data/features.yml,
// copiés dans src/data/ par scripts/prebuild.mjs : un push sur main suffit à mettre le site à jour.
import { defineConfig } from "astro/config";
import sitemap from "@astrojs/sitemap";

export default defineConfig({
  site: process.env.PUBLIC_SITE_URL ?? "https://lyvre.org",
  trailingSlash: "always",
  output: "static",
  build: { format: "directory" },
  integrations: [sitemap({ filter: (page) => !page.includes("/contact/merci/") })],
  // Aucun script en ligne : la CSP de nginx n'autorise que les fichiers du site (script-src 'self').
  vite: { build: { assetsInlineLimit: 0 } },
  i18n: { locales: ["fr"], defaultLocale: "fr", routing: { prefixDefaultLocale: false } },
});
