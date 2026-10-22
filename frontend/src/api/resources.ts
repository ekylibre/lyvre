// Accès aux ressources de l'API pour les écrans : listes (Query) et actions (mutations)
// avec les messages métier `notices` (design §5) affichés en notifications.
import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { notifications } from "@mantine/notifications";
import { api } from "./client";

export interface Notice { level: "success" | "info" | "warning" | "danger"; message: string }

export interface ListResponse<T, M = unknown> { items: T[]; meta?: M }

const COLORS: Record<Notice["level"], string> = {
  success: "lichen", info: "ardoise", warning: "paille", danger: "brique",
};

export function showNotices(notices: Notice[] | undefined): void {
  for (const n of notices ?? []) {
    notifications.show({
      color: COLORS[n.level] ?? "ardoise",
      message: n.message,
      autoClose: n.level === "danger" || n.level === "warning" ? false : 5000,
    });
  }
}

export function useList<T, M = unknown>(key: QueryKey, url: string, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: [...key, url],
    queryFn: () => api.get<ListResponse<T, M>>(url),
    enabled: options.enabled,
  });
}

/**
 * Action sur l'API : notifications des `notices`, puis rechargement des listes `invalidate`.
 * Les erreurs de formulaire (422) sont laissées au formulaire (`silent`).
 */
export function useAction<V, R extends { notices?: Notice[] } = { notices?: Notice[] }>(
  request: (vars: V) => Promise<R>,
  options: { invalidate?: QueryKey[]; silent?: boolean } = {},
) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: request,
    meta: { silent: options.silent ?? false },
    onSuccess: (data) => {
      showNotices(data?.notices);
      for (const key of options.invalidate ?? []) void client.invalidateQueries({ queryKey: key });
    },
  });
}
