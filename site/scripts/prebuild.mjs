// Prépare la construction du site à partir des sources du dépôt (jamais modifiées ici) :
// - data/changelog.yml et data/features.yml → src/data/ (lus par src/lib/data.ts), comparatif de la page À propos
//   (frontend/src/features/about/*.ts) → src/data/about/ ;
// - doc/images/*.png (captures du README, `make captures`) → src/assets/captures/ (optimisées par Astro) ;
// - logos de l'application → src/assets/brand/ et public/favicon.svg ;
// - couleurs de la charte (frontend/src/app/lyvre.css) → src/styles/tokens.css, thème clair et sombre ;
// - image de partage public/og.png.
// Le site se construit ainsi sans dupliquer ni données ni charte.
import { copyFileSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const SITE = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const ROOT = resolve(SITE, "..");
const at = (...p) => join(SITE, ...p);
const from = (...p) => join(ROOT, ...p);

function copy(src, dest) {
  mkdirSync(dirname(dest), { recursive: true });
  copyFileSync(src, dest);
}

// Données
for (const name of ["changelog.yml", "features.yml"]) copy(from("data", name), at("src/data", name));
// Comparatif de la page À propos de l'application (critères, logiciels, points forts, limites).
for (const name of ["comparison.ts", "competitors.ts", "openSourceVendors.ts"]) {
  copy(from("frontend/src/features/about", name), at("src/data/about", name));
}

// Captures
const images = from("doc/images");
for (const name of readdirSync(images).filter((n) => n.endsWith(".png"))) copy(join(images, name), at("src/assets/captures", name));

// Logos
for (const name of ["lyvre-symbole.svg", "lyvre-symbole-inverse.svg", "lyvre-favicon.svg"]) {
  copy(from("frontend/src/assets", name), at("src/assets/brand", name));
}
copy(from("frontend/src/assets/lyvre-favicon.svg"), at("public/favicon.svg"));

// Couleurs : les deux blocs de variables --lv-* de la charte, réécrits pour prefers-color-scheme.
const css = readFileSync(from("frontend/src/app/lyvre.css"), "utf8");
function block(selector) {
  const start = css.indexOf(selector);
  if (start < 0) throw new Error(`lyvre.css : bloc « ${selector} » introuvable`);
  const body = css.slice(css.indexOf("{", start) + 1, css.indexOf("}", start));
  const vars = body.split("\n").map((l) => l.trim()).filter((l) => l.startsWith("--lv-"));
  if (vars.length < 10) throw new Error(`lyvre.css : variables --lv-* attendues sous « ${selector} »`);
  return vars.map((v) => `  ${v}`).join("\n");
}
const light = block(':root[data-mantine-color-scheme="light"]');
const dark = block(':root[data-mantine-color-scheme="dark"]');
writeFileSync(
  at("src/styles/tokens.css"),
  `/* Généré par scripts/prebuild.mjs depuis frontend/src/app/lyvre.css : ne pas modifier. */\n` +
    `:root {\n  color-scheme: light dark;\n${light}\n}\n` +
    `@media (prefers-color-scheme: dark) {\n  :root {\n${dark.replace(/^/gm, "  ")}\n  }\n}\n`,
);

// Image de partage (1200 × 630) : symbole, nom, promesse.
const symbol = readFileSync(from("frontend/src/assets/lyvre-symbole-inverse.svg"), "utf8")
  .replace(/^<svg[^>]*>/, "")
  .replace(/<\/svg>\s*$/, "");
const og = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <rect width="1200" height="630" fill="#1E2421"/>
  <rect x="0" y="600" width="1200" height="30" fill="#2F6B4F"/>
  <svg x="90" y="150" width="300" height="300" viewBox="0 0 120 120">${symbol}</svg>
  <text x="440" y="300" font-family="DejaVu Sans, sans-serif" font-weight="700" font-size="120" fill="#F6F4EE">l<tspan fill="#D9A441">y</tspan>vre</text>
  <text x="446" y="380" font-family="DejaVu Sans, sans-serif" font-size="38" fill="#C9D2CC">La comptabilité libre, sobre et souveraine</text>
  <text x="446" y="436" font-family="DejaVu Sans, sans-serif" font-size="30" fill="#8A948E">Association · SCI · Exploitation agricole · Société</text>
</svg>`;
mkdirSync(at("public"), { recursive: true });
await sharp(Buffer.from(og)).png().toFile(at("public/og.png"));

console.log("prebuild : données, captures, logos, couleurs et image de partage prêts.");
