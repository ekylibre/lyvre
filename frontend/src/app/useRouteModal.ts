// Fenêtre de création / modification portée par l'URL (« /journals/new », « /products/3/edit ») :
// les anciennes adresses des formulaires Jinja ouvrent la liste avec la fenêtre (FM3).
import { useCallback } from "react";
import { useLocation, useNavigate, useParams } from "react-router";
import { useCan } from "../api/session";

export function useRouteModal(basePath: string, idParam?: string) {
  const { pathname } = useLocation();
  const params = useParams();
  const navigate = useNavigate();
  const base = basePath.replace(/\/$/, "");
  const id = idParam && params[idParam] ? Number(params[idParam]) : null;
  const can = useCan();
  // Lecture seule : l'adresse d'un formulaire affiche la liste, sans fenêtre de saisie.
  const mode: "new" | "edit" | null = !can.write ? null
    : pathname.replace(/\/$/, "").endsWith("/new") ? "new" : id !== null ? "edit" : null;
  const keep = window.location.search;
  const openNew = useCallback(() => navigate(`${base}/new${keep}`), [navigate, base, keep]);
  const openEdit = useCallback((recordId: number) => navigate(`${base}/${recordId}/edit${keep}`),
    [navigate, base, keep]);
  const close = useCallback(() => navigate(`${basePath}${keep}`), [navigate, basePath, keep]);
  return { mode, id, openNew, openEdit, close };
}
