// Lot F5 : immobilisation créée, tableau d'amortissement (linéaire, base 360, prorata au 15/03).
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("immobilisation : fiche et tableau d'amortissement", async ({ page }) => {
  const year = new Date().getFullYear();
  await login(page, "SCI E2E", "/assets/");
  await expect(page.getByText(/Registre seulement/)).toBeVisible();  // SCI : amortissements non comptabilisés par défaut
  await page.getByRole("button", { name: "Nouvelle immobilisation" }).click();
  const form = page.getByRole("dialog");
  await form.getByLabel(/^Libellé/).fill("Ordinateur portable");
  await form.getByRole("combobox", { name: "Compte" }).click();
  await page.getByRole("option", { name: /218300/ }).click();
  await form.getByLabel(/^Acquisition/).fill(`${year}-03-15`);
  await form.getByLabel(/^Mise en service/).fill(`${year}-03-15`);
  await form.getByLabel(/^Valeur d'origine/).fill("1800");
  await form.getByRole("button", { name: "Créer l'immobilisation" }).click();
  await expect(page.getByRole("heading", { name: "Ordinateur portable" })).toBeVisible();
  const first = page.getByRole("row", { name: new RegExp(`^${year}`) });
  await expect(first.getByRole("cell", { name: "286", exact: true })).toBeVisible();
  await expect(first.getByRole("cell", { name: /286,00/ }).first()).toBeVisible();
});
