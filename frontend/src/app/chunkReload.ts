// Chargement des pages paresseuses : un fichier de page introuvable (nouvelle version déployée
// pendant que l'onglet était ouvert, conteneur en cours de remplacement, connexion coupée) recharge
// la page une fois, pour reprendre le build en service, au lieu d'afficher l'erreur.

const RELOAD_KEY = "lyvre:chunk-reload";
/** Pas de second rechargement automatique avant ce délai : évite une boucle si le fichier manque vraiment. */
const RELOAD_GUARD_MS = 10_000;

const CHUNK_ERROR = /Failed to fetch dynamically imported module|error loading dynamically imported module|Importing a module script failed|Unable to preload CSS/i;

export function isChunkLoadError(error: unknown): boolean {
  return error instanceof Error && CHUNK_ERROR.test(error.message);
}

function reloadAllowed(now: number): boolean {
  try {
    const last = Number(sessionStorage.getItem(RELOAD_KEY));
    if (last && now - last < RELOAD_GUARD_MS) return false;
    sessionStorage.setItem(RELOAD_KEY, String(now));
  } catch {
    return false; // stockage indisponible : pas de garde contre la boucle, donc pas de rechargement
  }
  return true;
}

export async function loadWithReload<T>(load: () => Promise<T>, reload: () => void = () => window.location.reload()): Promise<T> {
  try {
    return await load();
  } catch (error) {
    if (isChunkLoadError(error) && reloadAllowed(Date.now())) {
      reload();
      return new Promise<T>(() => {}); // la page se recharge : rien d'autre à afficher
    }
    throw error;
  }
}
