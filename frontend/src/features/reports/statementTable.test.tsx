// Essai de l'interface (10/11/2026) : bilan avec brut, amortissements et net par ligne d'immobilisations.
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "../../test/render";
import { StatementTable, type StatementLine } from "./StatementTable";

const LINES: StatementLine[] = [
  { kind: "section", label: "Immobilisations corporelles" },
  { kind: "row", label: "Constructions", indent: 2, gross: 195228601, depreciation: 140949841, n: 54278760, p: null },
  { kind: "row", label: "Amortissements et dépréciations des immobilisations", indent: 1, n: 0, p: null, unallocated: true },
  { kind: "total", label: "TOTAL", n: 54278760, p: null },
];

describe("StatementTable", () => {
  it("affiche brut, amortissements et net, et masque le reste non rapproché nul", () => {
    renderWithProviders(<StatementTable title="Actif" lines={LINES} nLabel="Net N" pLabel="Net N-1" showPrevious={false} />);
    expect(screen.getByText("Brut")).toBeInTheDocument();
    expect(screen.getByText("Amort. et dépréc.")).toBeInTheDocument();
    expect(screen.getByText(/1\s952\s286,01/)).toBeInTheDocument();
    expect(screen.getByText(/^1\s409\s498,41/)).toBeInTheDocument();
    expect(screen.queryByText("Amortissements et dépréciations des immobilisations")).not.toBeInTheDocument();
  });

  it("sans brut, deux colonnes seulement", () => {
    renderWithProviders(<StatementTable title="Passif" lines={[{ kind: "row", label: "Capital", n: 100, p: null }]}
      nLabel="N" pLabel="N-1" showPrevious={false} />);
    expect(screen.queryByText("Brut")).not.toBeInTheDocument();
  });
});
