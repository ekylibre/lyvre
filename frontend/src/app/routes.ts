// Pages de la SPA : app/spa_routes.json (partagé avec Flask) → composants chargés à la demande.
import type { ComponentType } from "react";
import routesFile from "../../../app/spa_routes.json";

export interface SpaRoute {
  rule: string;
  endpoint: string;
  public?: boolean;
}

export const SPA_ROUTES: SpaRoute[] = routesFile.routes;

type PageModule = { default: ComponentType };

/** Une page par endpoint de spa_routes.json (vérifié par routes.test.ts). */
export const PAGES: Record<string, () => Promise<PageModule>> = {
  "auth.login": () => import("../features/auth/LoginPage"),
  "auth.select_instance": () => import("../features/auth/SelectInstancePage"),
};

/** Pages sans la mise en page de l'application (en-tête, menus). */
export const BARE_PAGES = new Set(["auth.login", "auth.select_instance"]);

/** Règle Flask → chemin react-router (« /purchases/<int:purchase_id> » → « /purchases/:purchase_id »). */
export function toRouterPath(rule: string): string {
  const path = rule.replace(/<(?:[a-z]+:)?(\w+)>/g, ":$1");
  return path.length > 1 && path.endsWith("/") ? path.slice(0, -1) : path;
}

const MATCHERS = SPA_ROUTES.map((route) => {
  const pattern = toRouterPath(route.rule)
    .split("/")
    .map((part) => (part.startsWith(":") ? "[^/]+" : part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")))
    .join("/");
  return new RegExp(`^${pattern}/?$`);
});

/** Le chemin est-il une page de la SPA (sinon : ancienne page, navigation complète) ? */
export function isSpaPath(url: string): boolean {
  const path = new URL(url, window.location.origin).pathname;
  return MATCHERS.some((re) => re.test(path));
}
