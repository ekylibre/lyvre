// Reçus fiscaux, émission (lot B.2) : don de l'année repris pour sa donatrice, émission du reçu
// annuel (numéro définitif), PDF téléchargeable.
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("reçus fiscaux : émettre puis télécharger un reçu", async ({ page }) => {
  const year = new Date().getFullYear();
  await login(page, "Asso Dons E2E", "/receipts/");
  await expect(page.getByRole("row", { name: /Donatrice E2E/ })).toContainText("Prêt");
  await page.getByRole("button", { name: "Émettre tout (1)" }).click();
  await page.getByRole("dialog", { name: `Émettre 1 reçu(s) ${year} ?` }).getByRole("button", { name: "Émettre" }).click();
  await expect(page.getByText("1 reçu(s) émis.")).toBeVisible();
  await expect(page.getByText(`Aucun don à reprendre pour ${year}.`)).toBeVisible();

  await page.getByRole("tab", { name: /Reçus émis/ }).click();
  const row = page.getByRole("row", { name: new RegExp(`${year}-00001`) });
  await expect(row).toContainText("Donatrice E2E");
  await expect(row).toContainText("50,00");
  const href = await row.getByRole("link", { name: "PDF" }).getAttribute("href");
  const resp = await page.request.get(href!);
  expect(resp.headers()["content-type"]).toContain("application/pdf");
});
