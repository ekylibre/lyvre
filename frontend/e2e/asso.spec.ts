// Parcours associatifs (phase G) : saisie manuelle mensuelle d'un indicateur, retrouvée au
// rechargement ; menus « Odoo » et « Indicateurs » réservés au plan associatif.
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("indicateurs : saisie manuelle du mois, conservée", async ({ page }) => {
  await login(page, "Association E2E", "/impact/manual");
  const revenue = page.getByLabel("CA Vinted");
  await revenue.fill("150,5");
  await page.getByLabel("Abonnés Vinted").fill("42");
  await page.getByRole("button", { name: "Enregistrer le mois" }).click();
  await expect(page.getByText(/Saisie enregistrée pour \d{4}-\d{2}\./)).toBeVisible();

  await page.reload();
  await expect(page.getByLabel("CA Vinted")).toHaveValue("150,5");
  await expect(page.getByLabel("Abonnés Vinted")).toHaveValue("42");
  const nav = page.getByRole("navigation");
  await expect(nav.getByText("Indicateurs", { exact: true })).toBeVisible();
  await expect(nav.getByText("Odoo", { exact: true })).toBeVisible();
});

test("plan SCI : pas d'écrans associatifs dans le menu", async ({ page }) => {
  await login(page, "SCI E2E", "/");
  const nav = page.getByRole("navigation");
  await expect(nav.getByText("Compta", { exact: true })).toBeVisible();
  await expect(nav.getByText("Indicateurs", { exact: true })).toHaveCount(0);
  await expect(nav.getByText("Odoo", { exact: true })).toHaveCount(0);
});
