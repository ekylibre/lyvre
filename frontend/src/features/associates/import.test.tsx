import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { notifications } from "@mantine/notifications";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import type { Analysis } from "./ImportAssociatesPage";

const calls: { url: string; fields: Record<string, string> }[] = [];
const ANALYSIS: Analysis = {
  ok: true, errors: [], line_errors: 0, needs_counterpart: true,
  counterparts: [{ value: "471", label: "471 — Compte d'attente" }],
  rows: [{ line: 2, name: "Pascal", errors: [] }],
  associates: [{ name: "Pascal", action: "create", account_code: "45510300", parts: { full: 0, usufruct: 300, bare: 0 },
    balance_cents: 8696308, balance_action: "entry", rate: null }],
  movements: [{ date: "2026-01-01", nominal_cents: 1000, parts: 300 }],
};

vi.mock("../../api/upload", () => ({
  upload: async (url: string, form: FormData) => {
    const fields: Record<string, string> = {};
    form.forEach((v, k) => { fields[k] = typeof v === "string" ? v : (v as File).name; });
    calls.push({ url, fields });
    if (url.endsWith("/preview")) return fields.file === "faux.csv" ? { ...ANALYSIS, ok: false, line_errors: 1,
      rows: [{ line: 3, name: "X", errors: ["nature « XX » inconnue (PP, US ou NP)"] }] } : ANALYSIS;
    return { notices: [] };
  },
}));

const { default: ImportAssociatesPage } = await import("./ImportAssociatesPage");
const fileInput = () => document.querySelector<HTMLInputElement>('input[type="file"]')!;
const ADMIN = { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } };

afterEach(() => { calls.length = 0; vi.restoreAllMocks(); });

describe("import des associés", () => {
  it("analyse, contrepartie des soldes, puis import", async () => {
    vi.spyOn(notifications, "show").mockReturnValue("id");
    const user = userEvent.setup();
    renderWithProviders(<ImportAssociatesPage />, { session: ADMIN });
    await user.upload(fileInput(), new File(["nom;nature"], "associes.csv", { type: "text/csv" }));
    expect(await screen.findByText("Pascal")).toBeTruthy();
    const button = screen.getByRole("button", { name: "Importer" });
    expect((button as HTMLButtonElement).disabled).toBe(true); // contrepartie à choisir
    await user.click(screen.getByRole("combobox", { name: /Compte de contrepartie/ }));
    await user.click(await screen.findByRole("option", { name: "471 — Compte d'attente" }));
    await user.click(button);
    await waitFor(() => expect(calls.at(-1)).toEqual({ url: "/api/v1/associates/import",
      fields: { file: "associes.csv", counterpart_code: "471" } }));
  });

  it("erreurs : import impossible", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ImportAssociatesPage />, { session: ADMIN });
    await user.upload(fileInput(), new File(["x"], "faux.csv", { type: "text/csv" }));
    expect(await screen.findByText(/Ligne 3 \(X\)/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Importer" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("réservé à l'administrateur", () => {
    renderWithProviders(<ImportAssociatesPage />);
    expect(screen.getByText("Réservé à l'administrateur de l'instance.")).toBeTruthy();
  });
});
