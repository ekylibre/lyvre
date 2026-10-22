// Parcours achats (phase F) : dépôt d'une facture PDF → lecture → formulaire prérempli → ligne
// complétée → facture comptabilisée, puis suppression. Qonto n'est pas configuré dans la base
// E2E : aucun envoi possible.
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

const PDF = decodeURIComponent(new URL("./files/facture-free.pdf", import.meta.url).pathname);

test("facture d'achat : dépôt du PDF, lecture, comptabilisation, suppression", async ({ page }) => {
  await login(page, "SCI E2E", "/purchases/new");
  await expect(page.getByText("Déposer la facture ici ou cliquer pour la choisir")).toBeVisible();
  await page.locator('input[type="file"]').setInputFiles(PDF);

  await expect(page.getByText("Valeurs lues dans le texte du PDF.")).toBeVisible();
  await expect(page.getByLabel("N° de facture")).toHaveValue("1400000013");
  await expect(page.getByLabel(/^TTC/)).toHaveValue("39,99");
  await expect(page.getByTitle("Pièce de la facture")).toBeVisible();
  await expect(page.getByText("Envoyer à Qonto")).toHaveCount(0);  // Qonto non configuré

  // Exercice de la base E2E : l'année en cours.
  await page.getByLabel(/^Date/).fill(`${new Date().getFullYear()}-09-02`);
  // Fournisseur inconnu de la base : création proposée, nom lu sur la facture.
  await expect(page.getByRole("combobox", { name: "Fournisseur" })).toHaveValue("+ Créer un fournisseur…");
  await expect(page.getByLabel("Nom du nouveau fournisseur")).toHaveValue("Free");
  // « Achats divers » n'a pas de compte dans le plan E2E : compte de charge choisi sur la ligne.
  const account = page.getByRole("combobox", { name: "Compte (ligne 1)" });
  await account.fill("606300");
  await page.keyboard.press("Escape");
  await expect(page.getByText("39,99 € / 39,99 €")).toBeVisible();
  await page.getByRole("button", { name: "Enregistrer la facture" }).click();

  await expect(page.getByText("Facture enregistrée et comptabilisée.")).toBeVisible();
  await expect(page).toHaveURL(/\/purchases\/\d+$/);
  await expect(page.getByRole("heading", { name: "Facture 1400000013" })).toBeVisible();
  await expect(page.getByText("Comptabilisée", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: /^AC-\d{4}-\d{4}$/ })).toBeVisible();

  await page.getByRole("button", { name: "Supprimer" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Supprimer" }).click();
  await expect(page.getByText(/Facture 1400000013 supprimée, ainsi que son écriture AC-/)).toBeVisible();
  await expect(page).toHaveURL(/\/purchases\/$/);
  await expect(page.getByText("Aucune facture d'achat.")).toBeVisible();
});
