// Comptabilité agricole (lots AG1.a à AG1.f) : exploitations fictives du jeu d'essai (tests/fixtures/agri) —
// bilan agricole et annexe des biens vivants, soldes intermédiaires, profil fiscal ; micro-BA en recettes et dépenses.
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("exploitation au réel : bilan agricole, biens vivants, soldes intermédiaires, fiscalité", async ({ page }) => {
  await login(page, "Exploitation A E2E", "/reports/bilan?fy_id=1");
  await expect(page.getByText("Biens vivants et en-cours (cycle long)")).toBeVisible();
  await expect(page.getByText("Annexe : biens vivants et en-cours de production")).toBeVisible();
  await expect(page.getByText("TOTAL GÉNÉRAL DE L'ACTIF")).toBeVisible();

  await page.goto("/reports/sig?fy_id=1");
  await expect(page.getByRole("heading", { name: "Soldes intermédiaires de gestion" })).toBeVisible();
  await expect(page.getByText("Excédent brut d'exploitation")).toBeVisible();
  await expect(page.getByRole("link", { name: "Exporter en XLSX" })).toBeVisible();

  await page.goto("/configuration/organization?tab=tax");
  await expect(page.getByText("Réel simplifié")).toBeVisible();

  await page.goto("/products/");
  await page.getByRole("button", { name: "Ajouter les articles agricoles" }).click();
  await expect(page.getByText(/article\(s\) agricole\(s\) ajouté\(s\)/)).toBeVisible();
  await expect(page.getByText("Engrais et amendement", { exact: true })).toBeVisible();
});

test("exploitation au micro-BA : recettes et dépenses par catégorie agricole", async ({ page }) => {
  await login(page, "Exploitation D E2E", "/simple/");
  await expect(page.getByRole("heading", { name: "Recettes et dépenses" })).toBeVisible();
  await expect(page.getByRole("navigation").getByText("Écritures")).toHaveCount(0);
  await expect(page.getByText("Marché du samedi").first()).toBeVisible();
  await page.goto("/simple/reports?tab=book&year=2025");
  await expect(page.getByRole("tab", { name: "Livre des recettes" })).toBeVisible();
  await expect(page.getByText("Vente de l'ancien motoculteur")).toBeVisible();
  await expect(page.getByText("exclue du micro-BA").first()).toBeVisible();
  await page.getByRole("tab", { name: "Micro-BA" }).click();
  await expect(page.getByText("Bénéfice forfaitaire")).toBeVisible();
});
