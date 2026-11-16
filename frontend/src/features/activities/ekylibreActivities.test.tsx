// Lot AG11.b : rattachement des activités Ekylibre et surfaces par campagne.
import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { EkylibreActivitiesTable, type EkylibreActivityRow } from "./EkylibreActivitiesPage";

const ITEMS: EkylibreActivityRow[] = [
  { ekylibre_id: 3, name: "Blé tendre", productions: 2, activity: { id: 7, name: "Blé tendre", how: "name", unit: "hectare" },
    proposal: null, campaigns: [{ year: 2026, surface_ha: "20.00", lyvre_ha: null, state: "new" }] },
  { ekylibre_id: 4, name: "Maïs grain", productions: 1, activity: null,
    proposal: { name: "Maïs grain", lexicon_reference: "corn" }, campaigns: [{ year: 2026, surface_ha: "4.00", lyvre_ha: null, state: "new" }] },
  { ekylibre_id: 5, name: "Prairie", productions: 1, activity: { id: 8, name: "Prairie", how: "ekylibre", unit: "hectare" },
    proposal: null, campaigns: [{ year: 2026, surface_ha: "0.35", lyvre_ha: "3.000", state: "conflict" }] },
];

describe("Activités depuis Ekylibre", () => {
  it("propose la cible, signale l'écart et envoie les choix", async () => {
    const onApply = vi.fn();
    renderWithProviders(<EkylibreActivitiesTable items={ITEMS} onApply={onApply}
      activities={[{ value: "7", label: "Blé tendre" }, { value: "8", label: "Prairie" }]} />);
    expect(screen.getByText("même nom")).toBeInTheDocument();
    expect(screen.getByText("production Lexicon reconnue")).toBeInTheDocument();
    expect(screen.getByText("2026 : 0,35 ha · saisie différente")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: "Retenir Prairie" }));
    await userEvent.click(screen.getByRole("button", { name: "Rattacher et reporter les surfaces (2)" }));
    expect(onApply).toHaveBeenCalledWith([{ ekylibre_id: 3, activity_id: 7 }, { ekylibre_id: 4, create: true }]);
  });
});
