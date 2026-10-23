// Comptabilité simplifiée (lot D) : menus sans partie double, recette saisie par catégorie,
// transaction du relevé catégorisée, états simplifiés, puis passage en partie double sans ressaisie.
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

  // États : compte de résultat par catégorie et situation de trésorerie.
  await page.goto("/simple/reports");
  await expect(page.getByRole("row", { name: /Cotisations/ })).toContainText("30,00");
  await expect(page.getByRole("row", { name: /Excédent/ })).toContainText("5,00");
  await page.getByRole("tab", { name: "Situation de trésorerie" }).click();
  await expect(page.getByRole("row", { name: /Banque simple/ })).toContainText("5,00");  // 30,00 encaissés − 25,00 payés

  // Passage en partie double, sans ressaisie : les opérations sont des écritures.
  await page.goto("/instances/");
  await page.getByRole("link", { name: "simple-e2e" }).click();
  await page.getByRole("button", { name: "Passer en partie double" }).click();
  await page.getByRole("dialog", { name: "Passer en partie double ?" }).getByRole("button", { name: "Passer en partie double" }).click();
  await expect(page.getByText("Partie double", { exact: true })).toBeVisible();
  await page.goto("/entries/");
  await expect(page.getByRole("navigation").getByText("Écritures")).toBeVisible();
  await expect(page.getByText("Cotisation Martin")).toBeVisible();
  await expect(page.getByText("CB PAPETERIE")).toBeVisible();
});
