// Dépôt de fichier avec progression (fetch ne la fournit pas) : multipart, CSRF, erreurs API.
import { ApiError, getCsrfToken } from "./client";

export function upload<T>(
  url: string,
  form: FormData,
  onProgress?: (percent: number) => void,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.setRequestHeader("X-CSRFToken", getCsrfToken());
    xhr.withCredentials = true;
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) onProgress(Math.round((event.loaded / event.total) * 100));
    };
    xhr.onerror = () => reject(new ApiError("network_error", "Serveur injoignable. Vérifiez la connexion.", 0));
    xhr.onload = () => {
      let data: { error?: { code?: string; message?: string; fields?: Record<string, string> } } | null = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        data = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(data as T);
        return;
      }
      const e = data?.error ?? {};
      reject(new ApiError(e.code ?? "http_error", e.message ?? `Erreur serveur (${xhr.status}).`,
        xhr.status, e.fields ?? {}));
    };
    xhr.send(form);
  });
}
