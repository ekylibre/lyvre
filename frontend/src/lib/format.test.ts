import { describe, expect, it } from "vitest";
import { formatEurosShort } from "./format";

describe("formatEurosShort", () => {
  it.each([
    [0, "0 €"], [950, "950 €"], [12345, "12,3 k€"], [-2500, "−2,5 k€"], [1500000, "1,5 M€"],
  ])("%d → %s", (euros, text) => expect(formatEurosShort(euros)).toBe(text));
});
