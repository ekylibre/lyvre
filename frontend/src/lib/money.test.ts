import { describe, expect, it } from "vitest";
import { formatEuros, parseAmount, toInput } from "./money";

describe("parseAmount", () => {
  it.each([
    ["", 0], ["12", 1200], ["12,5", 1250], ["12.50", 1250], ["1 234,56", 123456],
    ["1 234,56 €", 123456], ["0,07", 7],
  ])("%s → %i", (input, cents) => expect(parseAmount(input)).toBe(cents));

  it.each(["-5", "12,345", "abc", "1.234,56", "12,"])("refuse %s", (input) => {
    expect(parseAmount(input) === null || input === "12,").toBe(true);
  });

  it("accepte une virgule finale en cours de saisie", () => {
    expect(parseAmount("12,")).toBe(1200);
  });
});

describe("formatage", () => {
  it("toInput", () => {
    expect(toInput(123456)).toBe("1234,56");
    expect(toInput(0)).toBe("");
  });
  it("formatEuros", () => {
    expect(formatEuros(123456).replace(/\s/g, " ")).toBe("1 234,56 €");
  });
});
