import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import EntryForm, { type EntryFormProps } from "./EntryForm";

const ACCOUNTS = [
  { id: 1, code: "512", label: "Banque" },
  { id: 2, code: "606", label: "Achats non stockés" },
  { id: 3, code: "6061", label: "Électricité" },
];

type Call = { method: string; url: string; body: any };
let calls: Call[] = [];
let createResponse: { status: number; body: unknown } = {
  status: 201, body: { id: 10, reference: "AC-2026-0001", url: "/entries/10", reconciled: false, editable: true },
};

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  }));
}

beforeEach(() => {
  calls = [];
  localStorage.clear();
  window.showToast = vi.fn();
  vi.stubGlobal("fetch", vi.fn((url: string, init: RequestInit = {}) => {
    const method = init.method ?? "GET";
    const body = init.body ? JSON.parse(init.body as string) : undefined;
    calls.push({ method, url, body });
    if (url.startsWith("/api/v1/accounts")) {
      const q = new URL(url, "http://x").searchParams.get("q") ?? "";
      return json(200, { results: ACCOUNTS.filter((a) => a.code.startsWith(q) || a.label.toLowerCase().includes(q)) });
    }
    if (url === "/api/v1/entries/validate") return json(200, { errors: {} });
    if (url === "/api/v1/entries" && method === "POST") return json(createResponse.status, createResponse.body);
    return json(404, { error: { code: "not_found", message: "?" } });
  }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function props(over: Partial<EntryFormProps> = {}): EntryFormProps {
  return {
    mode: "create",
    fiscalYears: [{ id: 1, label: "2026", start_date: "2026-01-01", end_date: "2026-12-31" }],
    journals: [{ id: 1, code: "AC", label: "Achats" }],
    initial: { fiscal_year_id: 1, journal_id: 1, entry_date: "2026-03-15", description: "", lines: [] },
    urls: { api: "/api/v1", cancel: "/entries/" },
    recentsScope: "test",
    ...over,
  };
}

async function pickAccount(user: ReturnType<typeof userEvent.setup>, input: HTMLElement, query: string) {
  await user.click(input);
  await user.type(input, query);
  await screen.findAllByRole("option", { name: new RegExp(`^${query}`) });
  await user.keyboard("{Enter}");
}

const saveButton = () => screen.getByRole("button", { name: "Enregistrer" });

describe("EntryForm", () => {
  it("se saisit entièrement au clavier puis s'enregistre et enchaîne (US2)", async () => {
    const user = userEvent.setup();
    render(<EntryForm {...props()} />);

    await user.click(screen.getByLabelText("Description"));
    await user.keyboard("Facture EDF{Enter}");
    // Entrée dans la description → compte de la première ligne
    expect(screen.getByLabelText("Compte, ligne 1")).toHaveFocus();

    await user.keyboard("606");
    await screen.findAllByRole("option", { name: /^606/ });
    await user.keyboard("{Enter}{Tab}{Tab}84,50{Tab}{Tab}");
    expect(screen.getByLabelText("Compte, ligne 2")).toHaveFocus();
    await user.keyboard("512");
    await screen.findByRole("option", { name: /^512/ });
    await user.keyboard("{Enter}{Tab}{Tab}{Tab}=");   // « = » dans le crédit → écart
    expect(screen.getByLabelText("Crédit, ligne 2")).toHaveValue("84,50");

    await waitFor(() => expect(saveButton()).toBeEnabled());
    expect(screen.getByRole("status")).toHaveTextContent("Équilibrée");

    await user.keyboard("{Control>}{Enter}{/Control}");
    await waitFor(() => expect(calls.some((c) => c.url === "/api/v1/entries")).toBe(true));
    const post = calls.find((c) => c.url === "/api/v1/entries")!;
    expect(post.body).toMatchObject({
      fiscal_year_id: 1, journal_id: 1, entry_date: "2026-03-15", description: "Facture EDF",
      lines: [
        { account_id: 2, label: "Facture EDF", debit_cents: 8450, credit_cents: 0 },
        { account_id: 1, label: "Facture EDF", debit_cents: 0, credit_cents: 8450 },
      ],
    });

    // Enregistrer et enchaîner : formulaire vidé, exercice / journal / date conservés.
    await waitFor(() => expect(screen.getByLabelText("Description")).toHaveFocus());
    expect(screen.getByLabelText("Description")).toHaveValue("");
    expect(screen.getByLabelText("Compte, ligne 1")).toHaveValue("");
    expect(screen.getByLabelText("Date")).toHaveValue("2026-03-15");
    expect(window.showToast).toHaveBeenCalledWith("success", "Écriture AC-2026-0001 enregistrée.");
  });

  it("bloque l'enregistrement tant que l'écriture est déséquilibrée", async () => {
    const user = userEvent.setup();
    render(<EntryForm {...props()} />);
    await pickAccount(user, screen.getByLabelText("Compte, ligne 1"), "606");
    await user.type(screen.getByLabelText("Débit, ligne 1"), "100");
    await pickAccount(user, screen.getByLabelText("Compte, ligne 2"), "512");
    await user.type(screen.getByLabelText("Crédit, ligne 2"), "60");

    expect(screen.getByRole("status")).toHaveTextContent(/Écart : 40,00/);
    expect(saveButton()).toBeDisabled();
    await user.keyboard("{Control>}{Enter}{/Control}");
    expect(calls.some((c) => c.url === "/api/v1/entries")).toBe(false);
  });

  it("Entrée dans un montant de la dernière ligne ajoute une ligne préremplie avec l'écart", async () => {
    const user = userEvent.setup();
    render(<EntryForm {...props()} />);
    await user.type(screen.getByLabelText("Débit, ligne 1"), "100");
    await user.type(screen.getByLabelText("Crédit, ligne 2"), "30{Enter}");

    expect(screen.getByLabelText("Crédit, ligne 3")).toHaveValue("70,00");
    expect(screen.getByLabelText("Compte, ligne 3")).toHaveFocus();
  });

  it("signale un montant mal saisi", async () => {
    const user = userEvent.setup();
    render(<EntryForm {...props()} />);
    await user.type(screen.getByLabelText("Débit, ligne 1"), "12,345");
    expect(screen.getByText("Montant invalide.")).toBeInTheDocument();
    expect(saveButton()).toBeDisabled();
  });

  it("affiche les erreurs du serveur sous la cellule concernée", async () => {
    createResponse = {
      status: 422,
      body: { error: { code: "validation_error", message: "L'écriture contient des erreurs.",
                       fields: { "lines[0].account_id": "Compte d'en-tête non utilisable." } } },
    };
    const user = userEvent.setup();
    render(<EntryForm {...props({
      initial: {
        fiscal_year_id: 1, journal_id: 1, entry_date: "2026-03-15", description: "Test",
        lines: [
          { account: ACCOUNTS[1], debit_cents: 500 },
          { account: ACCOUNTS[0], credit_cents: 500 },
        ],
      },
    })} />);

    await waitFor(() => expect(saveButton()).toBeEnabled());
    await user.click(saveButton());
    const message = await screen.findByText("Compte d'en-tête non utilisable.");
    const input = screen.getByLabelText("Compte, ligne 1");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input.getAttribute("aria-describedby")).toBe(message.id);
    expect(window.showToast).toHaveBeenCalledWith("danger", "L'écriture contient des erreurs.");
  });

  it("supprime la ligne courante avec Ctrl+Suppr", async () => {
    const user = userEvent.setup();
    render(<EntryForm {...props()} />);
    await user.type(screen.getByLabelText("Débit, ligne 1"), "10");
    await user.type(screen.getByLabelText("Crédit, ligne 2"), "10{Enter}");
    expect(screen.getAllByRole("row")).toHaveLength(5); // en-tête + 3 lignes + pied
    await user.keyboard("{Control>}{Delete}{/Control}");
    const body = screen.getAllByRole("rowgroup")[1];
    expect(within(body).getAllByRole("row")).toHaveLength(2);
  });
});
