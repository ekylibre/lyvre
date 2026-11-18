// Adresses et éditeur du site. Les adresses viennent des variables de construction (docker/site.Dockerfile),
// avec les valeurs de production par défaut.
export const SITE_URL = import.meta.env.PUBLIC_SITE_URL ?? "https://lyvre.org";
export const DEMO_URL = import.meta.env.PUBLIC_DEMO_URL ?? "https://demo.lyvre.org";
export const REPO_URL = "https://github.com/ekylibre/lyvre";
export const DOC_URL = `${REPO_URL}/blob/main/doc`;
export const CONTACT_EMAIL = import.meta.env.PUBLIC_CONTACT_EMAIL ?? "contact@lyvre.org";

/** Identifiants publics de la démonstration (données fictives, remises à zéro chaque nuit). */
export const DEMO_LOGIN = {
  email: import.meta.env.PUBLIC_DEMO_EMAIL ?? "demo@lyvre.org",
  password: import.meta.env.PUBLIC_DEMO_PASSWORD ?? "demo-lyvre",
};

export const NAV = [
  { href: "/fonctionnalites/", label: "Fonctionnalités" },
  { href: "/comparatif/", label: "Comparatif" },
  { href: "/nouveautes/", label: "Nouveautés" },
  { href: "/installer/", label: "Installer" },
  { href: "/contact/", label: "Contact" },
];
