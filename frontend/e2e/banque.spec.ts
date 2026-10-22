// Parcours banque (phase E) : rapprocher au clavier (Entrée), annuler (Ctrl+Z), créer
// l'écriture d'une transaction sans suggestion (N) dans le panneau latéral.
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("rapprochement : Entrée, Ctrl+Z, puis création de l'écriture avec N", async ({ page }) => {
  await login(page, "SCI E2E", "/reconciliation/");
  await expect(page.getByText("2 transactions à rapprocher sur 2")).toBeVisible();
  await expect(page.getByText("BQ-E2E-1")).toBeVisible();  // suggestion de la 1re transaction

  const region = page.getByRole("region", { name: /Transactions à rapprocher/ });
  await region.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("1 transaction à rapprocher sur 2")).toBeVisible();
  await expect(page.getByText("1 transaction rapprochée.")).toBeVisible();

  await region.focus();
  await page.keyboard.press("Control+z");
  await expect(page.getByText("Action annulée.")).toBeVisible();
  await expect(page.getByText("2 transactions à rapprocher sur 2")).toBeVisible();

  // Le crédit sans écriture : panneau de saisie, contrepartie au compte 706000.
  await region.focus();
  await page.keyboard.press("j");
  await page.keyboard.press("n");
  const panel = page.getByRole("dialog", { name: "Créer l'écriture" });
  await expect(panel.getByLabel("Compte, ligne 1")).toHaveValue(/512000/);
  await expect(panel.getByLabel("Compte, ligne 2")).toBeFocused();
  await page.keyboard.type("706");
  await page.getByRole("option", { name: /706000/ }).click();
  await panel.getByLabel("Crédit, ligne 2").click();
  await page.keyboard.press("=");
  await panel.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect(page.getByText(/Écriture BQ-\d{4}-\d{4} créée et rapprochée\./)).toBeVisible();
  await expect(panel).toBeHidden();
  await expect(page.getByText("1 transaction à rapprocher sur 2")).toBeVisible();
});

test("comptes bancaires et transactions du compte", async ({ page }) => {
  await login(page, "SCI E2E", "/bank-accounts/");
  await page.getByRole("link", { name: "Banque E2E" }).click();
  await expect(page.getByRole("heading", { name: "Banque E2E" })).toBeVisible();
  await page.locator("label", { hasText: "À rapprocher" }).click();
  await expect(page.getByText("CB LEROY MERLIN")).toBeVisible();
});
