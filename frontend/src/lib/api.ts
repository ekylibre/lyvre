import type { FieldErrors } from "./types";

/** Erreur renvoyée par /api/v1 (format { error: { code, message, fields } }). */
export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
    public fields: FieldErrors = {},
  ) {
    super(message);
  }
}

function csrfToken(): string {
  return document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')?.content ?? "";
}

export async function api<T>(
  method: "GET" | "POST" | "PUT" | "DELETE",
  url: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET") {
    headers["Content-Type"] = "application/json";
    headers["X-CSRFToken"] = csrfToken();
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
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const error = data?.error ?? {};
    if (response.status === 401) {
      throw new ApiError("unauthenticated", "Session expirée : reconnectez-vous.", 401);
    }
    throw new ApiError(
      error.code ?? "http_error",
      error.message ?? `Erreur serveur (${response.status}).`,
      response.status,
      error.fields ?? {},
    );
  }
  return data as T;
}
