// Lot AG8.c : champ « Affectation analytique » (activités par atelier, puis clés).
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "../test/render";
import { AnalyticSelect, groupTargets } from "./AnalyticSelect";

const TARGETS = [{ value: "activity:2", label: "Blé", group: "Grandes cultures" }, { value: "activity:3", label: "Maïs", group: "Grandes cultures" },
  { value: "key:1", label: "Surface cultures", group: "Clés de répartition" }];

describe("Affectation analytique", () => {
  it("regroupe par atelier et n'affiche rien sans activité", () => {
    expect(groupTargets(TARGETS)).toEqual([
      { group: "Grandes cultures", items: [{ value: "activity:2", label: "Blé" }, { value: "activity:3", label: "Maïs" }] },
      { group: "Clés de répartition", items: [{ value: "key:1", label: "Surface cultures" }] }]);
    renderWithProviders(<><AnalyticSelect aria-label="Vide" targets={[]} value={null} onChange={() => {}} />
      <AnalyticSelect aria-label="Analytique" targets={TARGETS} value="key:1" onChange={() => {}} /></>);
    expect(screen.queryByLabelText("Vide")).toBeNull();
    expect(screen.getAllByLabelText("Analytique")[0]).toHaveValue("Surface cultures");
  });
});
