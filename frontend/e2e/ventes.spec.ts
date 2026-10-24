// Module Ventes (lot S7) : facture sans Qonto de bout en bout (saisie, émission, PDF, encaissement
// par la transaction bancaire), loyer mensuel jusqu'à la quittance, abonnement d'achat dont les
// échéances passées sont signalées manquantes.
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

const year = new Date().getFullYear();
const iso = (d: Date) => d.toISOString().slice(0, 10);

test("facture : saisie, émission, PDF, encaissement", async ({ page }) => {
  await login(page, "SCI Ventes E2E", "/sales/new");
  await page.getByRole("combobox", { name: "Client" }).click();
  await page.getByRole("option", { name: "Client Ventes E2E" }).click();
  await page.getByLabel("Désignation (ligne 1)").fill("Conseil en gestion");
  await page.getByLabel("Prix unitaire HT (ligne 1)").fill("1200");
  await page.getByRole("button", { name: "Enregistrer le brouillon" }).click();
  await expect(page.getByRole("heading", { name: "Facture brouillon" })).toBeVisible();

  await page.getByRole("button", { name: "Émettre" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Émettre" }).click();
  await expect(page.getByRole("heading", { name: `Facture F-${year}-0001` })).toBeVisible();
  await expect(page.getByRole("link", { name: "PDF" })).toHaveAttribute("href", /\/api\/v1\/sales\/\d+\/pdf/);
  await expect(page.getByText("TVA non applicable", { exact: false })).toHaveCount(1);

  await page.getByRole("button", { name: "Encaisser" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("radio", { name: /VIR CLIENT VENTES E2E/ }).check();
  await dialog.getByRole("button", { name: "Encaisser" }).click();
  await expect(page.getByText("Payée", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("restant dû")).toBeVisible();

  // Lot F3 : facture et encaissement lettrés sans action, sur le compte du client.
  await page.goto("/lettering/");
  await page.getByText("Lettrées", { exact: true }).click();
  await expect(page.getByTitle("Lettré").first()).toBeVisible();
  await expect(page.getByRole("link", { name: new RegExp(`^VE-${year}-`) })).toBeVisible();
});

test("bail : avis d'échéance émis, encaissé, quittance", async ({ page }) => {
  await login(page, "SCI Ventes E2E", "/leases/");
  await page.getByRole("link", { name: "Nouveau bail" }).click();
  await page.getByRole("combobox", { name: "Locataire (preneur)" }).click();
  await page.getByRole("option", { name: "Client Ventes E2E" }).click();
  await page.getByRole("combobox", { name: "Type de bail" }).click();
  await page.getByRole("option", { name: "Bail d'habitation" }).click();
  await page.getByLabel(/^Désignation/).fill("Appartement 2B");
  const first = new Date();
  first.setDate(1);  // échéance le 1er : la première est celle du mois en cours
  await page.getByLabel(/^Date d'effet/).fill(iso(first));
  await page.getByRole("button", { name: "Suivant" }).click();
  // Étape 2 : un bien au forfait (cas simple, sans carte).
  await page.getByRole("button", { name: "Ajouter un bien" }).click();
  const item = page.getByRole("dialog");
  await item.getByLabel(/^Désignation/).fill("Appartement");
  await item.getByText("Forfait").click();
  await item.getByRole("button", { name: "Ajouter" }).click();
  await expect(page.getByRole("cell", { name: "Appartement", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Suivant" }).click();
  // Étape 3 : 9 600 € par an, soit 800 € par mois, plus 50 € de charges.
  await page.getByLabel("Prix Appartement").fill("9600");
  await page.getByLabel(/^Provisions sur charges/).fill("50");
  await page.getByRole("button", { name: "Valider le bail" }).click();
  await expect(page.getByRole("heading", { name: "Appartement 2B", exact: true })).toBeVisible();
  await expect(page.getByText(/^Rédigé le /)).toBeVisible();  // texte du bail figé à la validation (lot L2)
  await expect(page.getByRole("link", { name: "Aperçu (PDF)" })).toHaveAttribute("href", /\/preview\.pdf$/);

  await page.goto("/sales/due");
  await expect(page.getByText("1 échéance(s) préparée(s) à l'instant.")).toBeVisible();
  await page.getByRole("checkbox").nth(1).check();
  await page.getByRole("button", { name: "Émettre (1)" }).click();
  await expect(page.getByText("Aucune échéance à émettre.")).toBeVisible();

  await page.goto("/leases/");
  await page.getByRole("link", { name: "Appartement 2B" }).click();
  await page.getByRole("link", { name: new RegExp(`F-${year}-`) }).click();
  await page.getByRole("button", { name: "Encaisser" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByText("Chèque, espèces…").click();
  await dialog.getByRole("textbox", { name: "Encaissé sur" }).or(dialog.getByRole("combobox", { name: "Encaissé sur" })).click();
  await page.getByRole("option", { name: "Banque Ventes" }).click();
  await dialog.getByRole("button", { name: "Encaisser" }).click();
  await expect(page.getByRole("button", { name: "Quittance" })).toBeVisible();
  const popup = page.waitForEvent("popup");
  await page.getByRole("button", { name: "Quittance" }).click();
  await (await popup).close();

  await page.goto("/leases/");
  await page.getByRole("link", { name: "Appartement 2B" }).click();
  await expect(page.getByText(/^Quittance /)).toBeVisible();
});

test("abonnement : échéances passées sans facture signalées", async ({ page }) => {
  await login(page, "SCI Ventes E2E", "/subscriptions/");
  await page.getByRole("button", { name: "Nouvel abonnement" }).click();
  const form = page.getByRole("dialog");
  await form.getByLabel(/^Désignation/).fill("Box internet");
  await form.getByRole("combobox", { name: "Fournisseur" }).click();
  await page.getByRole("option", { name: "Orange E2E" }).click();
  await form.getByLabel(/^Montant TTC/).fill("45");
  const start = new Date();
  start.setMonth(start.getMonth() - 3, 1);
  await form.getByLabel(/^Début/).fill(iso(start));
  await form.getByRole("button", { name: "Créer l'abonnement" }).click();
  await expect(page.getByRole("heading", { name: "Box internet" })).toBeVisible();
  await expect(page.getByText("Manquante").first()).toBeVisible();
});

test("produit constaté d'avance proposé à la clôture (lot F4)", async ({ page }) => {
  await login(page, "SCI Ventes E2E", "/sales/");
  const csrf = (await (await page.request.get("/api/v1/session")).json()).csrf_token;
  const call = async (method: string, url: string, data?: unknown) => {
    const resp = await page.request.fetch(url, { method, data, headers: { "X-CSRFToken": csrf } });
    expect(resp.ok(), await resp.text()).toBeTruthy();
    return resp.json();
  };
  const client = (await call("GET", "/api/v1/sales/form-options")).clients.find((c: { label: string }) => c.label === "Client Ventes E2E").value;
  const sale = (await call("POST", "/api/v1/sales", { entity_id: client, issue_date: iso(new Date()),
    service_start: `${year}-12-01`, service_end: `${year + 1}-11-30`,
    lines: [{ label: "Maintenance annuelle", quantity: "1", unit_price: "3650", vat_rate: "0", account_code: "706" }] })).item;
  await call("POST", `/api/v1/sales/${sale.id}/issue`);
  const fy = (await call("GET", "/api/v1/fiscal-years")).items.find((f: { label: string }) => f.label === String(year));

  await page.goto(`/fiscal-years/${fy.id}/closing`);
  await page.getByRole("button", { name: /2\. Écritures d'inventaire/ }).click();
  await expect(page.getByText("Propositions de charges et produits constatés d'avance")).toBeVisible();
  await page.getByLabel(/^Retenir F-/).check();
  await page.getByRole("button", { name: "Passer les écritures (1)" }).click();
  await expect(page.getByText("passée", { exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: /Produit constaté d'avance/ }).first()).toBeVisible();
});

test("modèles de bail : livrés, à relire (lot L2)", async ({ page }) => {
  await login(page, "SCI Ventes E2E", "/lease-templates/");
  await expect(page.getByRole("tab", { name: /Bail dérogatoire commercial/ })).toBeVisible();
  await expect(page.getByText("Modèle livré, à relire")).toBeVisible();
  await page.getByRole("tab", { name: /Bail d'habitation/ }).click();
  await expect(page.getByText("CONTRAT DE LOCATION")).toBeVisible();
});

test("bail : bien choisi sur la carte (lot L3)", async ({ page }) => {
  // Aucun appel extérieur : services géographiques de Lyvre et tuiles IGN interceptés.
  const parcel = { type: "Polygon", coordinates: [[[-0.7840, 45.8270], [-0.7830, 45.8270], [-0.7830, 45.8277], [-0.7840, 45.8277], [-0.7840, 45.8270]]] };
  await page.route("https://data.geopf.fr/**", (r) => r.fulfill({ status: 200, contentType: "image/png",
    body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==", "base64") }));
  await page.route("**/api/v1/geo/organization", (r) => r.fulfill({ json: { center: { lat: 45.82735, lon: -0.7835, zoom: 17, label: "SCI", insee: "17387" } } }));
  await page.route("**/api/v1/geo/parcels?**", (r) => r.fulfill({ json: { type: "FeatureCollection", features: [{ type: "Feature", id: "17387000AH0248",
    geometry: parcel, properties: { idu: "17387000AH0248", ref: "AH 248", insee: "17387", commune: "Saint-Porchaire", area_m2: 5619 } }] } }));
  await page.route("**/api/v1/geo/parcel?lat=**", (r) => r.fulfill({ json: { item: { idu: "17387000AH0248", ref: "AH 248", area_m2: 5619,
    buildings: 2, buildings_area_m2: 155, commune: "ST PORCHAIRE" } } }));

  await page.setViewportSize({ width: 1920, height: 1080 });  // grand écran : la fenêtre chevauche la carte
  await login(page, "SCI Ventes E2E", "/leases/new");
  await page.getByRole("combobox", { name: "Locataire (preneur)" }).click();
  await page.getByRole("option", { name: "Client Ventes E2E" }).click();
  await page.getByRole("combobox", { name: "Type de bail" }).click();
  await page.getByRole("option", { name: "Bail dérogatoire commercial" }).click();
  await page.getByLabel(/^Désignation/).fill("La Vauzelle E2E");
  await page.getByRole("button", { name: "Suivant" }).click();
  await page.getByText("Avec carte").click();
  await page.locator("[data-testid=lease-map] path.leaflet-interactive").first().click();
  await expect(page.getByText("Total : 5 619 m²")).toBeVisible();
  await expect(page.getByText("2 bât. · 155 m²")).toBeVisible();  // fiche Lexicon
  await page.getByRole("button", { name: "Valider la sélection" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel(/^Références cadastrales/)).toHaveValue("AH 248");
  await expect(dialog.getByLabel(/^Surface louée/)).toHaveValue("5619");
  await expect(dialog.getByLabel(/^Dont surface bâtie/)).toHaveValue("155");
  // La fenêtre passe au-dessus de la carte : les couches de Leaflet laissent passer les clics
  // (pointer-events: none) même quand elles la recouvrent ; on les rend « cliquables » le temps de
  // demander au navigateur l'élément affiché au centre du champ.
  const label = dialog.getByLabel(/^Désignation/);
  const field = (await label.boundingBox())!;
  const onTop = await page.evaluate(({ x, y }) => {
    const panes = [...document.querySelectorAll<HTMLElement>(".leaflet-container, .leaflet-container *")];
    panes.forEach((el) => el.style.setProperty("pointer-events", "auto", "important"));
    const hit = document.elementFromPoint(x, y);
    panes.forEach((el) => el.style.removeProperty("pointer-events"));
    return hit?.closest("[role=dialog]") ? "fenêtre" : hit?.closest(".leaflet-container") ? "carte" : String(hit?.tagName);
  }, { x: field.x + field.width / 2, y: field.y + field.height / 2 });
  expect(onTop).toBe("fenêtre");
  await label.fill("Potager");
  await dialog.getByRole("button", { name: "Ajouter" }).click();
  await expect(page.getByRole("cell", { name: "Potager", exact: true })).toBeVisible();
  await expect(page.locator("[data-testid=lease-map] .lease-letter")).toHaveText("A");

  // Zone dessinée (Bâtiment) à cheval sur la parcelle : surface calculée, parcelle touchée reprise.
  await page.getByText("Dessiner").click();
  await page.getByText("Bâtiment", { exact: true }).click();
  const box = (await page.getByTestId("lease-map").boundingBox())!;
  const at = (dx: number, dy: number) => page.mouse.click(box.x + box.width / 2 + dx, box.y + box.height / 2 + dy);
  await at(-40, -30);
  await at(40, -30);
  await at(40, 30);
  await at(-40, 30);
  await at(-40, -30);  // fermeture sur le premier point
  await expect(page.getByText(/^Zone de .* m²/)).toBeVisible();
  await page.getByRole("button", { name: "Valider la sélection" }).click();
  const zone = page.getByRole("dialog");
  await expect(zone.getByLabel(/^Références cadastrales/)).toHaveValue("AH 248");
  await zone.getByLabel(/^Désignation/).fill("Atelier");
  await zone.getByRole("button", { name: "Ajouter" }).click();
  await expect(page.getByRole("cell", { name: "Atelier", exact: true })).toBeVisible();
  await expect(page.locator("[data-testid=lease-map] .lease-letter")).toHaveText(["A", "B"]);
});
