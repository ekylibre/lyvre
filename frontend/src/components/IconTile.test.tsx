// Lot NV4 : pastilles d'icônes, pictogrammes agric et icône automatique des en-têtes de page.
import { describe, expect, it } from "vitest";
import { renderWithProviders, TEST_SESSION } from "../test/render";
import { IconTile } from "./IconTile";
import { PageHeader } from "./PageHeader";
import { Pictogram } from "./Pictogram";
import { PICTOGRAMS } from "./pictograms.generated";

const SESSION = { ...TEST_SESSION, nav: [
  { key: "compta", label: "Compta", icon: "calculator", items: [
    { key: "entries", label: "Écritures", url: "/entries/", icon: "notebook-pen", also_urls: ["/lettering/"] },
    { key: "stock", label: "Inventaire de clôture", url: "/inventory/", icon: "boxes", pictogram: "silo" },
  ] },
] };

describe("pictogrammes et pastilles", () => {
  it("les formes blanches d'agric deviennent des découpes", () => {
    expect(PICTOGRAMS.fertilization.cuts.length).toBeGreaterThan(0);
    const { container } = renderWithProviders(<Pictogram name="fertilization" />);
    expect(container.querySelector("mask")).not.toBeNull();
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });

  it("le pictogramme l'emporte sur l'icône, rien sans l'un ni l'autre", () => {
    const { container } = renderWithProviders(<><IconTile icon="boxes" pictogram="silo" /><IconTile /></>);
    expect(container.querySelector("[data-pictogram=silo]")).not.toBeNull();
    expect(container.querySelector(".lucide-boxes")).toBeNull();
    expect(container.querySelectorAll("svg")).toHaveLength(1);
  });

  it("en-tête : icône de l'entrée de menu de la page, onglets compris", () => {
    const lettering = renderWithProviders(<PageHeader title="Lettrage" />, { session: SESSION, route: "/lettering/" });
    expect(lettering.container.querySelector(".lucide-notebook-pen")).not.toBeNull();
    lettering.unmount();
    const stock = renderWithProviders(<PageHeader title="Inventaire" />, { session: SESSION, route: "/inventory/12" });
    expect(stock.container.querySelector("[data-pictogram=silo]")).not.toBeNull();
    stock.unmount();
    const none = renderWithProviders(<PageHeader title="Autre" icon={null} />, { session: SESSION, route: "/entries/" });
    expect(none.container.querySelector("svg")).toBeNull();
  });
});
