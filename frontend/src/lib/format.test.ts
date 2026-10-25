import { describe, expect, it } from "vitest";
import { formatEurosShort, formatNaf } from "./format";

describe("formatEurosShort", () => {
  it.each([
    [0, "0 €"], [950, "950 €"], [12345, "12,3 k€"], [-2500, "−2,5 k€"], [1500000, "1,5 M€"],
  ])("%d → %s", (euros, text) => expect(formatEurosShort(euros)).toBe(text));
});

describe("formatNaf", () => {
  it("ajoute le point du code officiel", () => {
    expect(formatNaf("6820B")).toBe("68.20B");
    expect(formatNaf(null)).toBe("");
  });
});
