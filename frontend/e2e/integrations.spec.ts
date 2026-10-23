// Intégrations selon la structure (lots I1 à I5) : liste et logos d'une SCI, proposition de Qonto,
// écrans silencieux sans Qonto, action qui a besoin de SMTP.
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("SCI : intégrations de la structure, logos, Qonto recommandée", async ({ page }) => {
  await login(page, "SCI E2E", "/configuration/integrations/");
  await expect(page.getByRole("heading", { name: "Intégrations" })).toBeVisible();
  await expect(page.getByAltText("Qonto")).toBeVisible();
  await expect(page.getByText("Recommandée")).toBeVisible();
  await expect(page.getByText("HelloAsso", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Google Analytics (GA4)")).toHaveCount(0);
  // Qonto désactivée : la page des factures d'achat n'en parle pas.
  await page.goto("/purchases/");
  await expect(page.getByText("Factures fournisseurs saisies dans l'application.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Synchroniser les factures Qonto" })).toHaveCount(0);
  await expect(page.getByText(/Qonto indisponible/)).toHaveCount(0);
});

test("tableau de bord : proposer Qonto, puis ne plus le proposer", async ({ page }) => {
  await login(page, "SCI Associés E2E", "/");
  const card = page.getByRole("alert").filter({ hasText: "Activez Qonto" });
  await expect(card).toBeVisible();
  await expect(card.getByRole("link", { name: "Configurer" })).toHaveAttribute("href", "/configuration/integrations/qonto");
  await card.getByRole("button", { name: "Ne plus proposer" }).click();
  await expect(page.getByText("Activez Qonto")).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Tableau de bord" })).toBeVisible();
  await expect(page.getByText("Activez Qonto")).toHaveCount(0);
});

test("relance sans SMTP : l'action dit qu'elle a besoin de l'intégration", async ({ page }) => {
  await login(page, "Association E2E", "/entities/members");
  await page.getByRole("button", { name: "Relancer les échus" }).click();
  const dialog = page.getByRole("dialog", { name: "Intégration SMTP (emails) désactivée" });
  await expect(dialog.getByText("La relance par email nécessite l'intégration SMTP (emails), désactivée.")).toBeVisible();
  await expect(dialog.getByRole("link", { name: "Activer l'intégration" })).toHaveAttribute("href", "/configuration/integrations/smtp");
});
