import { describe, expect, it } from "vitest";
import { BARE_PAGES, PAGES, SPA_ROUTES, isSpaPath, toRouterPath } from "./routes";

describe("routes de la SPA", () => {
  it("une page pour chaque endpoint de spa_routes.json, et inversement", () => {
    const endpoints = SPA_ROUTES.map((r) => r.endpoint).sort();
    expect(Object.keys(PAGES).sort()).toEqual(endpoints);
    for (const page of BARE_PAGES) expect(endpoints).toContain(page);
  });

  it("convertit les règles Flask", () => {
    expect(toRouterPath("/purchases/<int:purchase_id>")).toBe("/purchases/:purchase_id");
    expect(toRouterPath("/journals/")).toBe("/journals");
    expect(toRouterPath("/")).toBe("/");
  });

  it("reconnaît les chemins servis par la SPA", () => {
    expect(isSpaPath("/login")).toBe(true);
    expect(isSpaPath("/login?next=/entries/")).toBe(true);
    expect(isSpaPath("/select-instance/")).toBe(true);
    expect(isSpaPath("/purchases/")).toBe(false);
    expect(isSpaPath("/")).toBe(true);
  });
});
