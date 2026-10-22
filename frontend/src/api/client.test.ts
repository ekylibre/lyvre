import { describe, expect, it } from "vitest";
import { query, safeNext } from "./client";
import { merge } from "./session";

describe("client", () => {
  it("ne suit `next` que vers une page de l'application", () => {
    expect(safeNext("/entries/?fy=2")).toBe("/entries/?fy=2");
    expect(safeNext("https://evil.example")).toBe("/");
    expect(safeNext("//evil.example")).toBe("/");
    expect(safeNext("/\\evil.example")).toBe("/");
    expect(safeNext(null, "/select-instance")).toBe("/select-instance");
  });

  it("construit les paramètres sans valeurs vides", () => {
    expect(query({ q: "edf", page: 2, month: "", unpaid: false, hidden: true })).toBe("?q=edf&page=2&hidden=true");
    expect(query({})).toBe("");
  });

  it("fusionne les préférences (null supprime, ou est gardé pour l'envoi)", () => {
    const base = { color_scheme: "dark" as const, tables: { a: { hidden: ["x"] } } };
    expect(merge(base, { tables: { a: null } } as never)).toEqual({ color_scheme: "dark", tables: {} });
    expect(merge({}, { tables: { a: null } } as never, true)).toEqual({ tables: { a: null } });
  });
});
