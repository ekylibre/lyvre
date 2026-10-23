// Reçus fiscaux (lots B.2, B.3) : don de l'année repris pour sa donatrice, émission en arrière-plan
// (numéro définitif), PDF téléchargeable, annulation avec réémission, état annuel.
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("reçus fiscaux : émettre, télécharger, annuler et réémettre, état annuel", async ({ page }) => {
  const year = new Date().getFullYear();
  await login(page, "Asso Dons E2E", "/receipts/");
  await expect(page.getByRole("row", { name: /Donatrice E2E/ })).toContainText("Prêt");
  await page.getByRole("button", { name: "Émettre tout (1)" }).click();
  await page.getByRole("dialog", { name: `Émettre 1 reçu(s) ${year} ?` }).getByRole("button", { name: "Émettre" }).click();
  await expect(page.getByText("Émission terminée")).toBeVisible();
  await expect(page.getByText("1 reçu(s) émis, 0 donateur(s) à compléter.")).toBeVisible();
  await expect(page.getByText(`Aucun don à reprendre pour ${year}.`)).toBeVisible();

  await page.getByRole("tab", { name: /Reçus émis/ }).click();
  const first = page.getByRole("row", { name: new RegExp(`${year}-00001`) });
  await expect(first).toContainText("Donatrice E2E");
  await expect(first).toContainText("50,00");
  const href = await first.getByRole("link", { name: "PDF" }).getAttribute("href");
  expect((await page.request.get(href!)).headers()["content-type"]).toContain("application/pdf");

  await first.getByRole("button", { name: "Annuler…" }).click();
  const dialog = page.getByRole("dialog", { name: `Annuler le reçu ${year}-00001` });
  await dialog.getByLabel("Motif").fill("Adresse corrigée");
  await dialog.getByRole("button", { name: "Annuler et réémettre" }).click();
  await expect(page.getByText(`Reçu ${year}-00001 annulé, remplacé par le reçu ${year}-00002.`)).toBeVisible();
  await expect(first).toContainText("Annulé");
  await expect(page.getByRole("row", { name: new RegExp(`^${year}-00002`) })).toContainText("Émis");

  await page.getByRole("tab", { name: "État annuel" }).click();
  await expect(page.getByText("1 annulé(s)")).toBeVisible();
  await expect(page.getByRole("row", { name: /dont repris sur un reçu émis/ })).toContainText("50,00");
});
