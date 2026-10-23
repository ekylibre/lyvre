// Appels à l'API JSON /api/v1 depuis la SPA (claudedocs/design_front_mantine.md §5, §7).
// Session par cookie (même origine), jeton CSRF en en-tête, erreurs typées.
import type { FieldErrors } from "../lib/types";

/** Erreur renvoyée par /api/v1 (format { error: { code, message, fields } }). */
export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
    public fields: FieldErrors = {},
    /** Corps complet de l'erreur (données propres à un code, ex. `duplicates`). */
    public details: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

let csrfToken =
  document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')?.content ?? "";

/** Jeton renvoyé par l'API de session (il change à la connexion). */
export function setCsrfToken(token: string): void {
  if (token) csrfToken = token;
}

/** `next` n'est suivi que s'il désigne une page de l'application (chemin relatif). */
export function safeNext(next: string | null | undefined, fallback = "/"): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) {
    return fallback;
  }
  return next;
}

function currentPath(): string {
  return window.location.pathname + window.location.search;
}

/** Redirections de session : 401 → connexion, 409 no_instance → choix de l'instance,
 * 403 password_change_required → choix du mot de passe. */
function redirectFor(error: ApiError): void {
  const next = encodeURIComponent(currentPath());
  if (error.status === 401 && window.location.pathname !== "/login") {
    window.location.assign(`/login?next=${next}`);
  } else if (error.code === "no_instance" && window.location.pathname !== "/select-instance") {
    window.location.assign(`/select-instance?next=${next}`);
  } else if (error.code === "password_change_required" && window.location.pathname !== "/password") {
    window.location.assign(`/password?next=${next}`);
  }
}

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

interface RequestOptions {
  body?: unknown;
  signal?: AbortSignal;
  /** false : pas de redirection sur 401 / 409 (ex. lecture de la session sur /login). */
  redirect?: boolean;
}

export async function request<T>(method: Method, url: string, options: RequestOptions = {}): Promise<T> {
  const { body, signal, redirect = true } = options;
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET") {
    headers["Content-Type"] = "application/json";
    headers["X-CSRFToken"] = csrfToken;
  }
  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers,
      credentials: "same-origin",
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError("network_error", "Serveur injoignable. Vérifiez la connexion.", 0);
  }
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const e = data?.error ?? {};
    const error = new ApiError(
      e.code ?? "http_error",
      e.message ?? `Erreur serveur (${response.status}).`,
      response.status,
      e.fields ?? {},
      e,
    );
    if (redirect) redirectFor(error);
    throw error;
  }
  return data as T;
}

export const api = {
  get: <T>(url: string, options?: RequestOptions) => request<T>("GET", url, options),
  post: <T>(url: string, body?: unknown, options?: RequestOptions) =>
    request<T>("POST", url, { ...options, body }),
  patch: <T>(url: string, body?: unknown, options?: RequestOptions) =>
    request<T>("PATCH", url, { ...options, body }),
  put: <T>(url: string, body?: unknown, options?: RequestOptions) =>
    request<T>("PUT", url, { ...options, body }),
  delete: <T>(url: string, options?: RequestOptions) => request<T>("DELETE", url, options),
};

/** Paramètres de requête (valeurs vides omises). */
export function query(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === "" || value === false) continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export function getCsrfToken(): string {
  return csrfToken;
}
