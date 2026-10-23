// Module « Associés » (A1–A3) : l'administrateur active l'option, déclare deux associés, inscrit la
// souscription puis une donation avec réserve d'usufruit au registre, et saisit une note de frais
// portée au crédit du compte courant (relevé de la fiche associé).
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("associés : option, registre des parts, note de frais et compte courant", async ({ page }) => {
  await login(page, "SCI Associés E2E", "/configuration/organization");
  const menu = page.getByRole("navigation").getByText("Associés", { exact: true });
  await expect(menu).toHaveCount(0);
  await page.getByLabel("Société avec associés").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText("Identité de la structure enregistrée.")).toBeVisible();
  await expect(menu.first()).toBeVisible();  // menu (et sous-menu) rechargé avec la session

  // Deux associés, comptes courants 4551001 et 4551002.
  for (const name of ["Parent Martin", "Enfant Martin"]) {
    await page.goto("/associates/new");
    const dialog = page.getByRole("dialog", { name: "Nouvel associé" });
    await dialog.getByText("Nouveau tiers").click();
    await dialog.getByLabel("Nom").fill(name);
    await dialog.getByRole("button", { name: "Ajouter l'associé" }).click();
    await expect(page.getByText(new RegExp(`${name} ajouté aux associés`))).toBeVisible();
  }
  await expect(page.getByRole("cell", { name: "4551002" })).toBeVisible();

  // Registre : souscription de 1 000 parts de 10 €.
  await page.goto("/share-movements/new");
  let dialog = page.getByRole("dialog", { name: "Nouveau mouvement" });
  await dialog.getByLabel("Valeur nominale d'une part (€)").fill("10");
  await dialog.getByRole("combobox", { name: "Associé (ligne 1)" }).click();
  await page.getByRole("option", { name: "Parent Martin" }).click();
  await dialog.getByLabel("Parts (ligne 1)").fill("1000");
  await expect(dialog.getByText("Situation après le mouvement (1 000 parts)")).toBeVisible();
  await dialog.getByRole("button", { name: "Inscrire au registre" }).click();
  await expect(page.getByText(/Souscription enregistrée au registre/)).toBeVisible();

  // Donation de la nue-propriété de 300 parts, le parent garde l'usufruit.
  await page.goto("/share-movements/new");
  dialog = page.getByRole("dialog", { name: "Nouveau mouvement" });
  await dialog.getByRole("combobox", { name: "Type de mouvement" }).click();
  await page.getByRole("option", { name: "Donation" }).click();
  const line = async (i: number, who: string, direction: "reçoit" | "cède", parts: string, nature: string) => {
    if (i > 1) await dialog.getByRole("button", { name: "Ajouter une ligne" }).click();
    await dialog.getByRole("combobox", { name: `Associé (ligne ${i})` }).click();
    await page.getByRole("option", { name: who }).click();
    await dialog.getByRole("radiogroup", { name: `Sens (ligne ${i})` }).getByText(direction).click();
    await dialog.getByLabel(`Parts (ligne ${i})`).fill(parts);
    await dialog.getByRole("combobox", { name: `Nature (ligne ${i})` }).click();
    await page.getByRole("option", { name: nature }).click();
  };
  await line(1, "Parent Martin", "cède", "300", "Pleine propriété");
  await line(2, "Parent Martin", "reçoit", "300", "Usufruit");
  await line(3, "Enfant Martin", "reçoit", "300", "Nue-propriété");
  await expect(dialog.getByText("300 (30 %)").first()).toBeVisible();  // aperçu calculé par le serveur
  await dialog.getByRole("button", { name: "Inscrire au registre" }).click();
  await expect(page.getByText(/Donation enregistrée au registre/)).toBeVisible();
  await expect(page.getByText(/Capital du registre \(10 000,00 €\) différent du solde des comptes 101/)).toBeVisible();

  // Note de frais de l'enfant : 12,00 € portés au crédit de son compte courant.
  await page.goto("/associate-expenses/new");
  dialog = page.getByRole("dialog", { name: "Nouvelle note de frais" });
  await dialog.getByRole("combobox", { name: "Associé" }).click();
  await page.getByRole("option", { name: "Enfant Martin" }).click();
  await dialog.getByLabel("Libellé").fill("Ampoules");
  await dialog.getByRole("combobox", { name: "Compte de charge" }).click();
  await page.getByRole("option", { name: /606300/ }).click();
  await dialog.getByLabel("HT (€)").fill("12");
  await dialog.getByRole("button", { name: "Enregistrer la note de frais" }).click();
  await expect(page.getByText(/Note de frais de Enfant Martin enregistrée/)).toBeVisible();

  await page.goto("/associates/");
  await page.getByRole("link", { name: "Enfant Martin" }).click();
  await expect(page.getByRole("heading", { name: "Enfant Martin" })).toBeVisible();
  await expect(page.getByText("dû à l'associé").first()).toBeVisible();
  await expect(page.getByRole("cell", { name: "Note de frais", exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Nue-propriété", exact: true })).toBeVisible();  // parts détenues
});
