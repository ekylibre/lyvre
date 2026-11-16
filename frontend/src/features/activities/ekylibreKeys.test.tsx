// Lot AG11.c : clés depuis les interventions Ekylibre (parts par activité, règles proposées).
import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { EkylibreKeysView, type EkylibreKeysData } from "./EkylibreKeys";

const DATA: EkylibreKeysData = {
  fiscal_year: { id: 1, label: "2026" }, synced_at: "2026-11-07T10:00:00", interventions: 3, without_target: 1,
  keys: [
    { kind: "inputs", name: "Intrants (Ekylibre)", unit: "€", total: "300.00", unassigned: "100.00", members: [
      { activity_id: 1, activity: "Blé tendre", amount: "200.00", share_bp: 6667 },
      { activity_id: 2, activity: "Maïs grain", amount: "100.00", share_bp: 3333 }] },
    { kind: "hours", name: "Heures de matériel (Ekylibre)", unit: "h", total: "0.00", unassigned: "0.00", members: [] },
  ],
  rules: [
    { prefix: "601", label: "Achats d'approvisionnements", key: "Intrants (Ekylibre)", key_id: 5, existing: null },
    { prefix: "64", label: "Charges de personnel", key: "Main-d'œuvre (Ekylibre)", key_id: null, existing: null },
    { prefix: "6061", label: "Carburants", key: "Matériel (Ekylibre)", key_id: 6, existing: "Matériel" },
  ],
};

describe("Clés depuis Ekylibre", () => {
  it("affiche les parts et crée les règles cochées", async () => {
    const onRules = vi.fn();
    renderWithProviders(<EkylibreKeysView data={DATA} onCompute={vi.fn()} onRules={onRules} />);
    expect(screen.getByText("66,67 %")).toBeInTheDocument();
    expect(screen.getByText(/Non imputé .* 100 €/)).toBeInTheDocument();
    expect(screen.getByText("Rien à répartir.")).toBeInTheDocument();
    expect(screen.getByText("clé à calculer")).toBeInTheDocument();
    expect(screen.getByText("déjà : Matériel")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /^64/ })).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox", { name: /^601/ }));
    await userEvent.click(screen.getByRole("button", { name: "Créer les règles (1)" }));
    expect(onRules).toHaveBeenCalledWith(["601"]);
  });
});
