import { describe, expect, it } from "vitest";
import { delta, periodQuery } from "./types";

describe("Visibilité & Impact", () => {
  it("indique l'évolution et si elle est bonne", () => {
    expect(delta({ delta_pct: 12.34, higher_is_better: true })).toEqual({ text: "▲ 12,3 %", good: true });
    expect(delta({ delta_pct: -5, higher_is_better: false })).toEqual({ text: "▼ 5,0 %", good: true });
    expect(delta({ delta_pct: -5, higher_is_better: true })?.good).toBe(false);
    expect(delta({ delta_pct: null, higher_is_better: true })).toBeNull();
  });

  it("construit la requête de période sans les valeurs vides", () => {
    expect(periodQuery({ gran: "month", month: "2026-06", year: "" })).toBe("?gran=month&month=2026-06");
    expect(periodQuery({})).toBe("");
  });
});
