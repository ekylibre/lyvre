// Sirene (lot G3) : contrôle du SIREN, modal de proposition (à compléter cochés, différences non
// cochées, identiques masqués, unité cessée), bouton de la Structure selon la disponibilité.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import type { Session } from "../../api/session";
import OrganizationPage from "../../features/organization/OrganizationPage";
import { SireneProposalModal } from "./SireneProposalModal";
import { isValidSiren, type SireneProposal } from "./useSirene";

const RESULT: SireneProposal = {
  proposal: { name: "INSTITUT NATIONAL DE LA STATISTIQUE", siren: "120027016", address_line1: "88 avenue Verdier",
    city: "Montrouge", vat_number: "FR12120027016", naf_code: "8411Z", naf_nomenclature: "NAFRev2" },
  computed: ["vat_number"], state: "active", warnings: [],
  labels: { legal_form: null, naf: "Administration publique générale" }, existing_entity: null,
};
const FIELDS = { name: "Raison sociale", address_line1: "Adresse", city: "Ville", vat_number: "N° de TVA", naf_code: "Activité" };

describe("isValidSiren", () => {
  it.each([["120027016", true], ["120 027 016", true], ["120027017", false], ["12345", false], ["356000000", true]])(
    "%s → %s", (value, ok) => expect(isValidSiren(value)).toBe(ok));
});

describe("SireneProposalModal", () => {
  it("coche les champs vides, laisse les différences à choisir, masque les identiques", async () => {
    const onApply = vi.fn();
    renderWithProviders(<SireneProposalModal opened onClose={() => undefined} result={RESULT} fields={FIELDS} onApply={onApply}
      current={{ name: "Institut national de la statistique", address_line1: "1 rue Ancienne", city: "", vat_number: "", naf_code: "" }} />);
    expect(screen.queryByText("Raison sociale")).not.toBeInTheDocument();  // même nom, casse près
    expect(screen.getByRole("checkbox", { name: /Ville : Montrouge/ })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /Activité : 84.11Z — Administration publique générale/ })).toBeChecked();
    expect(screen.getByText("calculé")).toBeInTheDocument();
    const replace = screen.getByRole("checkbox", { name: "Remplacer Adresse" });
    expect(replace).not.toBeChecked();
    await userEvent.click(screen.getByRole("checkbox", { name: /Ville/ }));
    await userEvent.click(screen.getByRole("button", { name: "Reporter dans le formulaire" }));
    expect(onApply).toHaveBeenCalledWith({ vat_number: "FR12120027016", naf_code: "8411Z", naf_nomenclature: "NAFRev2" });
  });

  it("unité cessée : message, aucun champ", () => {
    renderWithProviders(<SireneProposalModal opened onClose={() => undefined} result={{ ...RESULT, state: "ceased" }}
      fields={FIELDS} onApply={() => undefined} current={{}} />);
    expect(screen.getByText(/aucun champ n'est proposé/)).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reporter dans le formulaire" })).not.toBeInTheDocument();
  });
});

describe("Structure", () => {
  const ORGANIZATION = {
    name: "Structure", siren: "120027016", rna: null, address_line1: null, address_line2: null, postal_code: null, city: null,
    country: "France", purpose: null, signatory_name: null, signatory_title: null, legal_form: null, rcs_city: null,
    vat_number: null, share_capital: "", naf_code: null, naf_nomenclature: null, rcs_mention: "", fec_ready: true,
    has_associates: false, associate_interest_rate: "0",
  };
  const admin = (sirene: boolean): Session => ({ ...TEST_SESSION, role: "admin", services: { sirene },
    permissions: { write: true, instance_admin: true } });
  let urls: string[];
  beforeEach(() => {
    urls = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL) => {
      const url = String(input);
      urls.push(url);
      const body = url.startsWith("/api/v1/sirene/proposal") ? RESULT : { item: ORGANIZATION };
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
    }) as typeof fetch);
  });
  afterEach(() => vi.restoreAllMocks());

  it("sans clé Sirene : pas de bouton", async () => {
    renderWithProviders(<OrganizationPage />, { session: admin(false) });
    await screen.findByLabelText("SIREN");
    expect(screen.queryByRole("button", { name: "Compléter depuis Sirene" })).not.toBeInTheDocument();
  });

  it("propose les champs puis remplit le formulaire, sans enregistrer", async () => {
    renderWithProviders(<OrganizationPage />, { session: admin(true) });
    await userEvent.click(await screen.findByRole("button", { name: "Compléter depuis Sirene" }));
    expect(urls).toContain("/api/v1/sirene/proposal?siren=120027016");
    expect(await screen.findByText(/le greffe du RCS et le capital/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reporter dans le formulaire" }));
    await waitFor(() => expect(screen.getByLabelText("Ville")).toHaveValue("Montrouge"));
    expect(screen.getByLabelText("Activité (code NAF)")).toHaveValue("84.11Z");
    expect(urls.filter((u) => u === "/api/v1/organization")).toHaveLength(1);  // lecture seule, pas d'enregistrement
  });
});
