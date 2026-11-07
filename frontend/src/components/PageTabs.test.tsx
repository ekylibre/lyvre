// Lot NV2 : onglets entre pages sœurs, adresses conservées.
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders, TEST_SESSION } from "../test/render";
import { ENTRY_TABS, PageTabs } from "./PageTabs";

describe("PageTabs", () => {
  it("sélectionne l'onglet de l'adresse courante", () => {
    renderWithProviders(<PageTabs tabs={ENTRY_TABS} />, { session: TEST_SESSION, route: "/lettering/" });
    expect(screen.getByRole("tab", { name: "Lettrage" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Écritures" })).toHaveAttribute("aria-selected", "false");
  });
});

describe("entrée active d'un onglet", () => {
  it("surligne l'entrée qui porte l'onglet", async () => {
    const { activeUrl } = await import("../app/AppShell/AppLayout");
    const menus = [{ key: "compta", label: "Compta", items: [
      { key: "entries", label: "Écritures", url: "/entries/", also_urls: ["/lettering/"] }] }];
    expect(activeUrl(menus, "/lettering/")).toBe("/entries/");
    expect(activeUrl(menus, "/entries/")).toBe("/entries/");
  });
});
