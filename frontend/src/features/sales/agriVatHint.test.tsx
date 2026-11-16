// Lot AG1.e : sur une exploitation agricole, un taux de TVA différent de celui de l'article du catalogue est signalé.
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import type { Session } from "../../api/session";
import { SaleLinesEditor } from "./SaleLinesEditor";
import { EMPTY_SALE_LINE, type SaleProductOption } from "./types";

const PRODUCTS: SaleProductOption[] = [{ value: "3", label: "Produit végétal", account: "7011", rate: "10", price: "",
  unit: "", description: "", nature: "goods" }];
const session = (chart: "agri" | "societe"): Session => ({ ...TEST_SESSION, instance: { ...TEST_SESSION.instance!, chart } });

function render(chart: "agri" | "societe", rate: string) {
  renderWithProviders(<SaleLinesEditor rows={[{ ...EMPTY_SALE_LINE, product_id: "3", label: "Blé", vat_rate: rate }]}
    onChange={() => undefined} products={PRODUCTS} accounts={[]} defaultAccount="7011" units={[]} projects={[]} exempt={false} />,
  { session: session(chart) });
}

describe("taux de TVA d'une vente agricole", () => {
  it("signale un taux différent de celui de l'article", () => {
    render("agri", "20");
    expect(screen.getByRole("status")).toHaveTextContent("Taux habituel de l'article : 10 %");
  });
  it("rien si le taux est celui de l'article", () => {
    render("agri", "10,0");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
  it("rien pour une société", () => {
    render("societe", "20");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
