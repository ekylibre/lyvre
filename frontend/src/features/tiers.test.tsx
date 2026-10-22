import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../test/render";
import { EntityForm } from "./entities/EntityForm";
import { filterQuery } from "./members/types";
import { formatHours } from "./work-times/WorkTimesPage";

afterEach(() => vi.restoreAllMocks());

describe("adhérents et temps", () => {
  it("garde seulement les filtres renseignés dans l'URL", () => {
    expect(filterQuery({ q: "dupont", date_from: "", sort_by: "status" })).toBe("?q=dupont&sort_by=status");
    expect(filterQuery({ q: "" })).toBe("");
  });
  it("affiche les heures à la française", () => {
    expect(formatHours(2.5)).toBe("2,50 h");
  });
});

describe("EntityForm", () => {
  it("envoie les champs et pose l'erreur de SIRET sur son champ", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ error: {
      code: "validation_error", message: "Le SIRET doit comporter 14 chiffres.",
      fields: { siret: "Le SIRET doit comporter 14 chiffres." } } }), { status: 422 }));
    const meta = { types: [{ value: "AUTRE", label: "Autre" }, { value: "FOURNISSEUR", label: "Fournisseur" }],
      products: [], integrations: {} as never };
    renderWithProviders(<EntityForm entity={null} meta={meta} onDone={() => {}} />);
    await userEvent.type(screen.getByLabelText(/Nom/), "EDF");
    await userEvent.type(screen.getByLabelText("SIRET"), "123");
    await userEvent.click(screen.getByLabelText("Bénévole"));
    await userEvent.click(screen.getByRole("button", { name: "Créer le tiers" }));
    expect(await screen.findByText("Le SIRET doit comporter 14 chiffres.")).toBeInTheDocument();
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]!.body));
    expect(body).toMatchObject({ name: "EDF", siret: "123", is_benevole: true, entity_type: "AUTRE" });
  });
});
