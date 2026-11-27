import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { VatMenu } from "./VatMenu";

const fy = { id: 1, label: "2026", vat_liable: true, vat_on_receipts: true, vat_period: null as "monthly" | "quarterly" | "annual" | null };
const open = async () => userEvent.click(screen.getByRole("button", { name: "TVA, exercice 2026" }));

describe("menu TVA d'un exercice", () => {
  it("un seul bouton dans la ligne, les cinq choix dans le menu", async () => {
    renderWithProviders(<VatMenu fy={fy} agri simple={false} onChange={vi.fn()} />);
    expect(screen.getAllByRole("button")).toHaveLength(1);
    await open();
    for (const name of ["Déclarer non soumis", "Option TVA sur les débits", "Déclaration mensuelle (CA3)",
      "Trimestrielle (CA3)", "Annuelle (CA12A)"]) expect(await screen.findByRole("menuitem", { name })).toBeTruthy();
  });

  it("envoie le rythme choisi", async () => {
    const onChange = vi.fn();
    renderWithProviders(<VatMenu fy={fy} agri simple={false} onChange={onChange} />);
    await open();
    await userEvent.click(await screen.findByRole("menuitem", { name: "Annuelle (CA12A)" }));
    expect(onChange).toHaveBeenCalledWith({ vat_period: "annual" });
  });

  it("le rythme actuel n'est plus proposé, mais peut être retiré", async () => {
    const onChange = vi.fn();
    renderWithProviders(<VatMenu fy={{ ...fy, vat_period: "annual" }} agri simple={false} onChange={onChange} />);
    await open();
    expect(screen.queryByRole("menuitem", { name: "Annuelle (CA12A)" })).toBeNull();
    await userEvent.click(await screen.findByRole("menuitem", { name: "Ne plus préparer la déclaration" }));
    expect(onChange).toHaveBeenCalledWith({ vat_period: null });
  });

  it("au clavier : Entrée ouvre, Échap ferme et rend le focus au bouton", async () => {
    renderWithProviders(<VatMenu fy={fy} agri simple={false} onChange={vi.fn()} />);
    const button = screen.getByRole("button", { name: "TVA, exercice 2026" });
    button.focus();
    await userEvent.keyboard("{Enter}");
    expect(await screen.findByRole("menuitem", { name: "Annuelle (CA12A)" })).toBeTruthy();
    await userEvent.keyboard("{Escape}");
    await vi.waitFor(() => expect(screen.queryByRole("menuitem", { name: "Annuelle (CA12A)" })).toBeNull());
    expect(document.activeElement).toBe(button);
  });

  it("hors régime agricole, pas de CA12A ; exercice non soumis, un seul choix", async () => {
    const { unmount } = renderWithProviders(<VatMenu fy={fy} agri={false} simple={false} onChange={vi.fn()} />);
    await open();
    expect(screen.queryByRole("menuitem", { name: "Annuelle (CA12A)" })).toBeNull();
    unmount();
    renderWithProviders(<VatMenu fy={{ ...fy, vat_liable: false }} agri simple={false} onChange={vi.fn()} />);
    await open();
    expect((await screen.findAllByRole("menuitem")).map((i) => i.textContent)).toEqual(["Déclarer soumis"]);
  });
});
