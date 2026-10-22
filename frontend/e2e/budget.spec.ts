// Budget (lot C.2) : saisie d'un budget (un compte en annuel, un autre par mois), enregistrement,
// puis rechargement de la page à l'identique.
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("budget : saisie annuelle et mensuelle, enregistrement et rechargement", async ({ page }) => {
  await login(page, "SCI E2E", "/budget/");
  const add = page.getByRole("combobox", { name: "Ajouter un compte" });
  await add.fill("606300");
  await page.getByRole("option", { name: /^606300/ }).click();
  await page.getByLabel("606300, annuel").fill("1200");
  await add.fill("706000");
  await page.getByRole("option", { name: /^706000/ }).click();
  await page.getByText("Mensuel").last().click();
  await page.getByLabel("706000, mois 1", { exact: true }).fill("500");
  await page.getByLabel("706000, mois 2", { exact: true }).fill("250");
  await expect(page.getByText("Modifications non enregistrées")).toBeVisible();
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText(/Budget \d{4} enregistré \(budget général\)/)).toBeVisible();

  await page.reload();
  await expect(page.getByLabel("606300, annuel")).toHaveValue("1 200,00");
  await expect(page.getByLabel("706000, mois 1", { exact: true })).toHaveValue("500,00");
  await expect(page.getByLabel("706000, mois 2", { exact: true })).toHaveValue("250,00");
  // 750 de produits − 1 200 de charges.
  await expect(page.getByRole("row", { name: /Résultat prévu/ }).getByText("−450,00 €")).toBeVisible();

  // Suivi : postes du budget (606300 : 45,00 € réalisés par BQ-E2E-1), export tableur.
  await page.getByRole("link", { name: "Suivi budgétaire" }).first().click();
  await expect(page.getByRole("heading", { name: "Suivi budgétaire" })).toBeVisible();
  await expect(page.getByRole("row", { name: /606300.*1 200,00/ })).toBeVisible();
  const href = await page.getByRole("link", { name: "Exporter (XLSX)" }).getAttribute("href");
  const resp = await page.request.get(href!);
  expect(resp.headers()["content-type"]).toContain("spreadsheetml");
});
