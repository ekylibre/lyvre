// Session de la SPA : utilisateur, instance, menus, préférences (GET /api/v1/session).
import { useCallback, useEffect, useRef } from "react";
import { useInRouterContext, useLocation } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api, setCsrfToken } from "./client";

// Lot NV1 : trois niveaux (menu › entrée ou sous-menu › entrée), icône Lucide et pictogramme agric.
export interface NavLink { key: string; label: string; url: string; icon?: string; pictogram?: string; also_urls?: string[] }
export interface NavDivider { divider: true }
export interface NavGroup { key: string; label: string; icon?: string; pictogram?: string; items: NavItem[] }
export type NavItem = NavLink | NavGroup | NavDivider;
export interface NavMenu { key: string; label: string; url?: string; icon?: string; pictogram?: string; items?: NavItem[] }

/** Entrées cliquables de l'arbre, avec le fil des libellés parents (recherche, entrée active). */
export function navLinks(menus: NavMenu[]): (NavLink & { trail: string[] })[] {
  const out: (NavLink & { trail: string[] })[] = [];
  const walk = (items: NavItem[], trail: string[]) => {
    for (const item of items) {
      if ("divider" in item) continue;
      if ("items" in item) walk(item.items, [...trail, item.label]);
      else out.push({ ...item, trail });
    }
  };
  for (const menu of menus) {
    if (menu.url) out.push({ key: menu.key, label: menu.label, url: menu.url, icon: menu.icon, pictogram: menu.pictogram, trail: [] });
    walk(menu.items ?? [], [menu.label]);
  }
  return out;
}

const pathOf = (url: string) => new URL(url, window.location.origin).pathname.replace(/\/$/, "") || "/";

/** URL du menu qui correspond le mieux à la page (préfixe le plus long : /entities/members
 * l'emporte sur /entities/ pour la page des adhérents). Tous niveaux (lot NV1). */
export function activeUrl(menus: NavMenu[], pathname: string): string | null {
  // Lot NV2 : une page rattachée (`also_urls`, un onglet) active l'entrée qui la porte.
  const candidates = navLinks(menus).flatMap((l) => [[l.url, l.url], ...(l.also_urls ?? []).map((a) => [a, l.url])]);
  const current = pathname.replace(/\/$/, "") || "/";
  const matches = candidates.filter(([u]) => {
    const path = pathOf(u);
    return path === "/" ? current === "/" : current === path || current.startsWith(`${path}/`);
  });
  return matches.sort(([a], [b]) => pathOf(b).length - pathOf(a).length)[0]?.[1] ?? null;
}

function useOptionalPathname(): string | null {
  // Hors routeur (rare : écrans d'erreur), pas d'entrée de menu.
  // eslint-disable-next-line react-hooks/rules-of-hooks
  return useInRouterContext() ? useLocation().pathname : null;
}

/** Entrée de menu de la page courante (lot NV4 : icône automatique des en-têtes de page). */
export function useNavEntry(): (NavLink & { trail: string[] }) | null {
  const pathname = useOptionalPathname();
  const nav = useCurrentSession().nav;
  if (pathname === null) return null;
  const url = activeUrl(nav, pathname);
  return url ? navLinks(nav).find((l) => l.url === url) ?? null : null;
}

export type ColorSchemePreference = "light" | "dark" | "auto";

export interface Preferences {
  color_scheme?: ColorSchemePreference;
  tables?: Record<string, { hidden?: string[] }>;
  /** Menu latéral replié en rail (lot NV4). */
  nav_rail?: boolean;
  [key: string]: unknown;
}

export interface DemoCredentials { email: string; password: string }

/** Identifiants de la démonstration, lus avant la connexion dans la page (balise meta `lyvre-demo`). */
export function demoCredentials(): DemoCredentials | null {
  const meta = document.querySelector<HTMLMetaElement>('meta[name="lyvre-demo"]');
  const email = meta?.dataset.email, password = meta?.dataset.password;
  return email && password ? { email, password } : null;
}

export type InstanceRole = "admin" | "treasurer" | "accountant";

export interface Session {
  user: { id: number; email: string; full_name: string | null; is_admin: boolean; must_change_password: boolean } | null;
  instance: { id: number; slug: string; label: string; chart: string; bookkeeping?: "double" | "simple";
    has_associates?: boolean;
    /** Intégrations activées ; `proposed` : recommandées à proposer (administrateur de l'instance). */
    integrations?: { enabled: string[]; proposed: string[]; scopes?: Record<string, string[]> } } | null;
  instances: { id: number; label: string }[];
  /** Rôle sur l'instance courante ; `permissions` en découle (le serveur reste seul juge). */
  role?: InstanceRole | null;
  permissions?: { write: boolean; instance_admin: boolean };
  nav: NavMenu[];
  admin_links: { label: string; url: string }[];
  preferences: Preferences;
  /** Version de Lyvre (data/changelog.yml) et commit déployé s'il est connu (lot R1). */
  app?: { version: string; commit: string };
  /** Services du serveur : Sirene si la clé de l'INSEE est configurée (lot G3). */
  services?: { sirene: boolean };
  /** Démonstration publique (LYVRE_DEMO) : identifiants partagés, bandeau ; absent ou null sinon. */
  demo?: DemoCredentials | null;
  csrf_token: string;
}

export const SESSION_KEY = ["session"] as const;

const ANONYMOUS: Session = {
  user: null, instance: null, instances: [], nav: [], admin_links: [], preferences: {}, csrf_token: "",
  role: null, permissions: { write: false, instance_admin: false },
};

function accept(session: Session): Session {
  setCsrfToken(session.csrf_token);
  return session;
}

/** Lecture de la session ; non connecté → session anonyme (pas de redirection ici). */
export async function fetchSession(): Promise<Session> {
  try {
    return accept(await api.get<Session>("/api/v1/session", { redirect: false }));
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return ANONYMOUS;
    throw err;
  }
}

export function useSession() {
  return useQuery({ queryKey: SESSION_KEY, queryFn: fetchSession, staleTime: 5 * 60_000 });
}

/** Session courante (disponible sous <SessionGate>). */
export function useCurrentSession(): Session {
  const { data } = useSession();
  return data ?? ANONYMOUS;
}

/**
 * Droits de l'utilisateur sur l'instance courante : `write` (tout sauf l'expert-comptable),
 * `instanceAdmin` (administrateur de l'instance). Sert à masquer les actions ; l'API refuse de
 * toute façon ce qui n'est pas permis.
 */
/** Démonstration publique (LYVRE_DEMO) : intégrations ni activables ni configurables. */
export function useDemo(): boolean {
  return !!useCurrentSession().demo;
}

export function useCan(): { write: boolean; instanceAdmin: boolean; role: InstanceRole | null } {
  const session = useCurrentSession();
  return {
    write: session.permissions?.write ?? true,
    instanceAdmin: session.permissions?.instance_admin ?? false,
    role: session.role ?? null,
  };
}

/** Intégration activée pour l'instance : sinon, rien de ce qui n'existe que par elle ne s'affiche
 * (boutons, colonnes, bandeaux). Les données déjà importées restent visibles. */
export function useIntegration(slug: string, scope?: string): boolean {
  const integrations = useCurrentSession().instance?.integrations;
  if (!integrations?.enabled.includes(slug)) return false;
  // Partie du périmètre (Qonto : transactions, purchases, sales) ; inconnue : périmètre par défaut.
  return !scope || (integrations.scopes?.[slug] ?? ["transactions", "purchases"]).includes(scope);
}

/** Mode de tenue de l'instance courante : partie double, ou comptabilité simplifiée (lot D). */
export function useBookkeeping(): "double" | "simple" {
  return useCurrentSession().instance?.bookkeeping ?? "double";
}

/** Structure tenue par une association (plan « asso ») : reçus fiscaux, adhérents, bénévolat,
 * fonds dédiés. Les autres structures (SCI) ne voient pas ces fonctions ; le serveur les refuse. */
export function useIsAssociation(): boolean {
  return (useCurrentSession().instance?.chart ?? "asso") === "asso";
}

export function useLogin() {
  const client = useQueryClient();
  return useMutation({
    meta: { silent: true },  // erreur affichée par le formulaire
    mutationFn: (credentials: { email: string; password: string }) =>
      api.post<Session>("/api/v1/session/login", credentials, { redirect: false }),
    onSuccess: (session) => {
      client.clear();
      client.setQueryData(SESSION_KEY, accept(session));
    },
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<Session>("/api/v1/session/logout", undefined, { redirect: false }),
    onSuccess: (session) => {
      client.clear();
      client.setQueryData(SESSION_KEY, accept(session));
    },
  });
}

/** Change d'instance : toutes les données en cache appartiennent à l'ancienne. */
export function useSelectInstance() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (instanceId: number) =>
      api.post<Session>("/api/v1/session/instance", { instance_id: instanceId }),
    onSuccess: (session) => {
      client.clear();
      client.setQueryData(SESSION_KEY, accept(session));
    },
  });
}

const SAVE_DELAY = 500;

/** Fusion profonde ; `null` supprime la clé (gardé tel quel si `keepNull`, pour l'envoi). */
export function merge(base: Preferences, patch: Preferences, keepNull = false): Preferences {
  const out: Preferences = { ...base };
  for (const [key, value] of Object.entries(patch)) {
    if (value === null && !keepNull) delete out[key];
    else if (value === null) out[key] = null;
    else if (value && typeof value === "object" && !Array.isArray(value)
      && out[key] && typeof out[key] === "object" && !Array.isArray(out[key])) {
      out[key] = merge(out[key] as Preferences, value as Preferences, keepNull);
    } else out[key] = value;
  }
  return out;
}

/**
 * Préférences du compte : mises à jour tout de suite dans le cache, envoyées au
 * serveur regroupées (PATCH fusionné après 500 ms sans changement).
 */
export function usePreferences(): [Preferences, (patch: Preferences) => void] {
  const client = useQueryClient();
  const preferences = useCurrentSession().preferences;
  const pending = useRef<Preferences>({});
  const timer = useRef<number | undefined>(undefined);

  const flush = useCallback(() => {
    const patch = pending.current;
    pending.current = {};
    timer.current = undefined;
    if (Object.keys(patch).length) {
      api.patch("/api/v1/me/preferences", patch).catch(() => undefined);
    }
  }, []);

  useEffect(() => () => {
    if (timer.current !== undefined) {
      window.clearTimeout(timer.current);
      flush();
    }
  }, [flush]);

  const update = useCallback((patch: Preferences) => {
    client.setQueryData<Session>(SESSION_KEY, (old) =>
      old ? { ...old, preferences: merge(old.preferences, patch) } : old);
    pending.current = merge(pending.current, patch, true);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(flush, SAVE_DELAY);
  }, [client, flush]);

  return [preferences, update];
}
