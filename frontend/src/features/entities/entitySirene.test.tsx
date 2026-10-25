// Sirene dans le tiers et la facture d'achat (lot G4) : recherche, proposition reportée dans le
// formulaire, alerte de SIREN déjà connu ; fournisseur connu repris, nouveau fournisseur à créer.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import type { Session } from "../../api/session";
import type { SireneCandidate, SireneProposal } from "../../components/sirene/useSirene";
import { SupplierSirene, type SupplierChoice } from "../purchases/SupplierSirene";
import { EntityForm } from "./EntityForm";

const CANDIDATE: SireneCandidate = { siren: "120027016", siret: "12002701600241", name: "INSEE", legal_form: null,
  postal_code: "86000", city: "Poitiers", head_office: false, active: true };
const proposal = (existing: SireneProposal["existing_entity"]): SireneProposal => ({
  proposal: { name: "INSEE", siren: "120027016", siret: "12002701600241", address_line1: "5 rue Sainte Catherine",
    postal_code: "86000", city: "Poitiers", country: "France", person_kind: "company", naf_code: "8411Z",
    naf_nomenclature: "NAFRev2", vat_number: "FR85120027016" },
  computed: ["vat_number"], state: "active", warnings: [], labels: { legal_form: null, naf: "Administration publique générale" },
  existing_entity: existing,
});
const SESSION: Session = { ...TEST_SESSION, services: { sirene: true } };

let existing: SireneProposal["existing_entity"] = null;
let urls: string[] = [];
beforeEach(() => {
  urls = [];
  existing = null;
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL) => {
    const url = String(input);
    urls.push(url);
    const body = url.startsWith("/api/v1/sirene/search") ? { items: [CANDIDATE] } : proposal(existing);
    return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
  }) as typeof fetch);
});
afterEach(() => vi.restoreAllMocks());

async function searchAndPick() {
  await userEvent.type(screen.getByLabelText("Nom, SIREN ou SIRET"), "insee");
  await userEvent.click(screen.getByRole("button", { name: "Rechercher" }));
  await userEvent.click(await screen.findByText("INSEE"));
}

describe("formulaire du tiers", () => {
  it("sans Sirene : pas de recherche", () => {
    renderWithProviders(<EntityForm entity={null} meta={undefined} onDone={() => undefined} />);
    expect(screen.queryByText("Masquer la recherche Sirene")).not.toBeInTheDocument();
  });

  it("recherche, proposition, report dans le formulaire", async () => {
    renderWithProviders(<EntityForm entity={null} meta={undefined} onDone={() => undefined} />, { session: SESSION });
    await searchAndPick();
    expect(urls).toContain("/api/v1/sirene/proposal?siret=12002701600241&for=entity");
    expect(await screen.findByRole("checkbox", { name: /Nature : Entreprise ou organisme/ })).toBeChecked();
    await userEvent.click(screen.getByRole("button", { name: "Reporter dans le formulaire" }));
    await waitFor(() => expect(screen.getByLabelText("Ville")).toHaveValue("Poitiers"));
    expect(screen.getByLabelText("SIRET")).toHaveValue("12002701600241");
    expect(screen.getByLabelText("Activité (code NAF)")).toHaveValue("84.11Z");
    expect(screen.getByText("Administration publique générale")).toBeInTheDocument();
  });

  it("SIREN déjà connu : alerte avec lien vers le tiers", async () => {
    existing = { id: 7, name: "Institut" };
    renderWithProviders(<EntityForm entity={null} meta={undefined} onDone={() => undefined} />, { session: SESSION });
    await searchAndPick();
    expect(await screen.findByRole("link", { name: "Institut" })).toHaveAttribute("href", "/entities/7");
  });
});

describe("facture d'achat : fournisseur dans Sirene", () => {
  it.each([
    [null, { kind: "new", name: "INSEE", siret: "12002701600241", vat: "FR85120027016" }],
    [{ id: 7, name: "Institut" }, { kind: "known", id: 7, name: "Institut" }],
  ])("tiers existant %o → choix", async (known, expected) => {
    existing = known;
    const onChoose = vi.fn<(choice: SupplierChoice) => void>();
    renderWithProviders(<SupplierSirene initialQuery="" onChoose={onChoose} />, { session: SESSION });
    await userEvent.click(screen.getByRole("button", { name: "Chercher dans Sirene" }));
    await searchAndPick();
    await waitFor(() => expect(onChoose).toHaveBeenCalled());
    const choice = onChoose.mock.calls[0][0];
    expect(choice).toMatchObject(expected);
    if (choice.kind === "new") expect(choice.entity).toEqual({ siren: "120027016", address_line1: "5 rue Sainte Catherine",
      postal_code: "86000", city: "Poitiers", country: "France", naf_code: "8411Z", naf_nomenclature: "NAFRev2", person_kind: "company" });
  });
});

describe("liste des tiers : mise à jour groupée", () => {
  it("lance la comparaison des tiers qui ont un SIREN", async () => {
    const { default: EntitiesPage } = await import("./EntitiesPage");
    const tiers = [{ id: 1, name: "INSEE", entity_type: "AUTRE", siren: "120027016", siret: null },
      { id: 2, name: "Sans numéro", entity_type: "AUTRE", siren: null, siret: null }];
    vi.mocked(globalThis.fetch).mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = String(input);
      urls.push(`${init.method ?? "GET"} ${url}`);
      const body = init.method === "POST" ? { job: { id: 9 }, count: 1 }
        : { items: tiers, meta: { types: [], products: [], integrations: { helloasso: {}, odoo: {}, smtp: {} } } };
      return Promise.resolve(new Response(JSON.stringify(body), { status: init.method === "POST" ? 202 : 200 }));
    }) as typeof fetch);
    renderWithProviders(<EntitiesPage />, { session: SESSION, route: "/entities/" });
    await userEvent.click(await screen.findByRole("button", { name: "Mettre à jour depuis Sirene (1 avec un SIREN)" }));
    await waitFor(() => expect(urls).toContain("POST /api/v1/entities/sirene-refresh"));
  });
});
