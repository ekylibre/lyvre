// Comptabilité simplifiée (lots D.2, D.3) : menus sans partie double, recette saisie par
// catégorie, transaction du relevé catégorisée.
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("comptabilité simplifiée : menus, recette saisie, relevé catégorisé", async ({ page }) => {
  await login(page, "Asso Simple E2E", "/simple/");
  await expect(page.getByRole("heading", { name: "Recettes et dépenses" })).toBeVisible();
  const nav = page.getByRole("navigation");
  await expect(nav.getByText("Recettes et dépenses")).toBeVisible();
  await expect(nav.getByText("Écritures")).toHaveCount(0);
  await expect(nav.getByText("Rapprochement")).toHaveCount(0);

  const year = new Date().getFullYear();
  await page.getByRole("button", { name: "Nouvelle recette" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvelle recette" });
  await dialog.getByRole("textbox", { name: /^Date/ }).fill(`15/01/${year}`);
  await dialog.getByRole("textbox", { name: /^Date/ }).press("Tab");
  await dialog.getByLabel("Montant").fill("30");
  await dialog.getByLabel("Libellé").fill("Cotisation Martin");
  await dialog.getByRole("combobox", { name: "Catégorie" }).click();
  await page.getByRole("option", { name: "Cotisations" }).click();
  await dialog.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText(/Opération enregistrée/)).toBeVisible();
  await expect(page.getByRole("row", { name: /Cotisation Martin/ })).toContainText("+30,00");

  await page.getByRole("tab", { name: "Relevé à catégoriser" }).click();
  await page.getByRole("combobox", { name: "Catégorie de CB PAPETERIE" }).click();
  await page.getByRole("option", { name: "Achats et fournitures" }).click();
  await expect(page.getByText(/Transaction catégorisée/)).toBeVisible();
  await expect(page.getByText("Tout le relevé est catégorisé.", { exact: false })).toBeVisible();
  await page.getByRole("tab", { name: "Opérations" }).click();
  await expect(page.getByRole("row", { name: /CB PAPETERIE/ })).toContainText("−25,00");
});
