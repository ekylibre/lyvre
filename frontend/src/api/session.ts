// Session de la SPA : utilisateur, instance, menus, préférences (GET /api/v1/session).
import { useCallback, useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api, setCsrfToken } from "./client";

export interface NavLink { key: string; label: string; url: string }
export interface NavDivider { divider: true }
export interface NavMenu { key: string; label: string; url?: string; items?: (NavLink | NavDivider)[] }

export type ColorSchemePreference = "light" | "dark" | "auto";

export interface Preferences {
  color_scheme?: ColorSchemePreference;
  tables?: Record<string, { hidden?: string[] }>;
  [key: string]: unknown;
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
  /** Services du serveur : Sirene si la clé de l'INSEE est configurée (lot G3). */
  services?: { sirene: boolean };
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
