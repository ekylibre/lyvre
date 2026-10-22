import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders, TEST_SESSION } from "../test/render";
import { Can } from "./Can";
import { DataGrid } from "./DataGrid";
import { writeOnly } from "./ReadOnlyPage";

const ACCOUNTANT = { ...TEST_SESSION, role: "accountant" as const, permissions: { write: false, instance_admin: false } };
const ADMIN = { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } };

const grid = (
  <DataGrid id="t" records={[{ id: 1, name: "BQ" }]} columns={[
    { accessor: "name", title: "Code" },
    { accessor: "actions", title: "", render: () => <button type="button">Supprimer</button> },
  ]} />
);

describe("lecture seule (expert-comptable)", () => {
  it("masque la colonne d'actions des tableaux", () => {
    renderWithProviders(grid, { session: ACCOUNTANT });
    expect(screen.getByText("BQ")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Supprimer" })).toBeNull();
  });

  it("garde la colonne d'actions pour le trésorier", () => {
    renderWithProviders(grid);
    expect(screen.getByRole("button", { name: "Supprimer" })).toBeTruthy();
  });

  it("Can : écriture et administration de l'instance", () => {
    const ui = <><Can><span>écrire</span></Can><Can admin><span>administrer</span></Can></>;
    const { unmount } = renderWithProviders(ui, { session: ACCOUNTANT });
    expect(screen.queryByText("écrire")).toBeNull();
    unmount();
    renderWithProviders(ui, { session: ADMIN });
    expect(screen.getByText("écrire")).toBeTruthy();
    expect(screen.getByText("administrer")).toBeTruthy();
  });

  it("writeOnly remplace un écran de saisie par un message", () => {
    const Page = writeOnly(() => <p>formulaire</p>, "Saisir une écriture", { href: "/entries/", label: "Voir les écritures." });
    renderWithProviders(<Page />, { session: ACCOUNTANT });
    expect(screen.getByText("Accès en lecture seule")).toBeTruthy();
    expect(screen.queryByText("formulaire")).toBeNull();
    expect(screen.getByRole("link", { name: "Voir les écritures." }).getAttribute("href")).toBe("/entries/");
  });
});
