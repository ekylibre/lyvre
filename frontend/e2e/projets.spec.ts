// Projets (lot C.1) : création de deux projets, ventilation d'une ligne de charge entre eux,
// charges reportées sur la liste des projets.
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("projets : création, ventilation d'une ligne, charges par projet", async ({ page }) => {
  await login(page, "SCI E2E", "/projects/new");
  for (const name of ["Festival", "Jardin"]) {
    if (name === "Jardin") await page.getByRole("button", { name: "Créer un projet" }).click();
    const dialog = page.getByRole("dialog", { name: "Créer un projet" });
    await dialog.getByLabel("Nom").fill(name);
    await dialog.getByRole("button", { name: "Créer le projet" }).click();
    await expect(page.getByText(`Projet « ${name} » créé.`)).toBeVisible();
  }

  await page.goto("/entries/");
  await page.getByRole("link", { name: "BQ-E2E-PROJ" }).click();
  const charge = page.getByRole("row", { name: /606300/ });
  await charge.getByRole("button", { name: "Affecter…" }).click();
  const dialog = page.getByRole("dialog", { name: "Projet — ligne 606300" });
  await dialog.getByText("Ventiler").click();
  await dialog.getByRole("combobox", { name: "Projet, part 1" }).click();
  await page.getByRole("option", { name: "Festival" }).click();
  await dialog.getByLabel("Montant, part 1").fill("60");
  await dialog.getByRole("combobox", { name: "Projet, part 2" }).click();
  await page.getByRole("option", { name: "Jardin" }).click();
  await dialog.getByLabel("Montant, part 2").fill("30");
  await dialog.getByRole("button", { name: "Ventiler la ligne" }).click();
  await expect(page.getByText("Ligne ventilée en 2 parts.")).toBeVisible();
  await expect(page.getByRole("row", { name: /606300/ })).toHaveCount(2);

  await page.goto("/projects/");
  await expect(page.getByRole("row", { name: /Festival.*60,00/ })).toBeVisible();
  await expect(page.getByRole("row", { name: /Jardin.*30,00/ })).toBeVisible();
});
