import { describe, expect, it } from "vitest";
import { cents, EMPTY_LINE, lineTotal, linesTotal, updateLine } from "./lines";

const line = (patch: Partial<typeof EMPTY_LINE>) => ({ ...EMPTY_LINE, ...patch });
const PRODUCTS = [{ value: "3", label: "Électricité", account: "6061", rate: "20" }];

describe("lignes d'achat", () => {
  it("lit les montants saisis", () => {
    expect(cents("1 234,56")).toBe(123456);
    expect(cents("-10")).toBe(-1000);
    expect(cents("")).toBeNull();
    expect(cents("abc")).toBeNull();
  });

  it("calcule le TTC depuis la TVA saisie ou le taux", () => {
    expect(lineTotal(line({ untaxed: "33,33", vat: "6,66" }))).toBe(3999);
    expect(lineTotal(line({ untaxed: "100", vat_rate: "5,5" }))).toBe(10550);
    expect(lineTotal(line({ untaxed: "100" }))).toBe(10000);
    expect(linesTotal([line({ untaxed: "100", vat_rate: "20" }), line({ untaxed: "-10" })])).toBe(11000);
  });

  it("vide la TVA quand le montant change et reprend le produit", () => {
    expect(updateLine(line({ untaxed: "10", vat: "2" }), "untaxed", "20", PRODUCTS).vat).toBe("");
    expect(updateLine(line({}), "product_id", "3", PRODUCTS)).toMatchObject({ account_code: "6061", vat_rate: "20", label: "Électricité" });
    expect(updateLine(line({ label: "Facture EDF" }), "product_id", "3", PRODUCTS).label).toBe("Facture EDF");
  });
});
