import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Workspace, { type WorkspaceProps } from "./Workspace";
import type { BankTransaction, Suggestion } from "../../lib/types";

const tx = (id: number, label: string, amount: number): BankTransaction => ({
  id, date: "2026-03-10", label, amount_cents: amount, reconciled: false,
  category: null, entity: null, entry: null, new_entry_url: `/entries/new?bt_id=${id}`,
});
const sugg = (line: number, score: number, amount: number): Suggestion => ({
  journal_line_id: line, entry_id: line, reference: `BQ-${line}`, entry_date: "2026-03-10",
  label: "E", account_code: "5121", amount_cents: amount, score,
});

let server: {
  transactions: BankTransaction[];
  suggestions: Record<number, Suggestion[]>;
  reconcileFails: Set<number>;
};
type Call = { method: string; url: string; body: any };
let calls: Call[];

function json(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  }));
}

beforeEach(() => {
  calls = [];
  localStorage.clear();
  window.showToast = vi.fn();
  window.history.replaceState(null, "", "/reconciliation/");
  server = {
    transactions: [tx(1, "PRLV EDF", -100), tx(2, "CB LEROY", -250), tx(3, "VIR HELLOASSO", 900)],
    suggestions: { 1: [sugg(11, 2, -100)], 2: [sugg(21, 2, -250), sugg(22, 2, -250)], 3: [sugg(31, 1, 900)] },
    reconcileFails: new Set(),
  };
  vi.stubGlobal("fetch", vi.fn((url: string, init: RequestInit = {}) => {
    const method = init.method ?? "GET";
    const body = init.body ? JSON.parse(init.body as string) : undefined;
    calls.push({ method, url, body });
    const counters = () => ({ unreconciled: server.transactions.length, total: 3 });
    if (url.startsWith("/api/v1/bank-accounts/1/transactions")) {
      return json(200, { transactions: server.transactions, counters: counters() });
    }
    const m = url.match(/bank-transactions\/(\d+)\/suggestions/);
    if (m) return json(200, { suggestions: server.suggestions[Number(m[1])] ?? [] });
    if (url === "/api/v1/reconciliations") {
      const results = body.items.map((i: any) => server.reconcileFails.has(i.bank_transaction_id)
        ? { bank_transaction_id: i.bank_transaction_id, status: "error", message: "Montant différent de celui de la transaction." }
        : { bank_transaction_id: i.bank_transaction_id, status: "ok" });
      const done = results.filter((r: any) => r.status === "ok").map((r: any) => r.bank_transaction_id);
      server.transactions = server.transactions.filter((t) => !done.includes(t.id));
      return json(200, {
        results, counters: counters(),
        undo: done.length ? { method: "POST", url: "/api/v1/reconciliations/delete", body: { bank_transaction_ids: done } } : null,
      });
    }
    if (url === "/api/v1/reconciliations/delete") {
      server.transactions = [tx(1, "PRLV EDF", -100), tx(2, "CB LEROY", -250), tx(3, "VIR HELLOASSO", 900)];
      return json(200, { results: [], counters: counters(), undo: null });
    }
    return json(404, { error: { code: "not_found", message: "?" } });
  }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const props: WorkspaceProps = {
  bankAccounts: [{ id: 1, label: "CA Courant", account: { id: 5, code: "5121", label: "CA" } }],
  bankAccountId: 1,
  month: "",
  monthOptions: [{ value: "2026-03", label: "Mars 2026" }],
  urls: { api: "/api/v1", page: "/reconciliation/" },
  entryForm: {
    fiscalYears: [{ id: 1, label: "2026", start_date: "2026-01-01", end_date: "2026-12-31" }],
    journals: [{ id: 2, code: "BQ", label: "Banque" }],
    defaultJournalId: 2,
    recentsScope: "test",
  },
};

const rows = () => within(screen.getAllByRole("rowgroup")[1]).queryAllByRole("row");
const region = () => screen.getByRole("region", { name: /Transactions à rapprocher/ });

async function ready() {
  await waitFor(() => expect(rows()).toHaveLength(3));
  await screen.findByText("BQ-11");
}

describe("ReconcileWorkspace", () => {
  it("rapproche la transaction active avec Entrée et passe à la suivante", async () => {
    const user = userEvent.setup();
    render(<Workspace {...props} />);
    await ready();
    region().focus();
    await user.keyboard("{Enter}");

    await waitFor(() => expect(rows()).toHaveLength(2));
    const post = calls.find((c) => c.url === "/api/v1/reconciliations")!;
    expect(post.body).toEqual({ items: [{ bank_transaction_id: 1, journal_line_id: 11 }] });
    expect(screen.getByRole("status")).toHaveTextContent("2 transactions non rapprochées sur 3");
    expect(rows()[0]).toHaveClass("table-primary"); // CB LEROY devient active
    expect(screen.getByText(/1 transaction rapprochée\./)).toBeInTheDocument();
  });

  it("refuse Entrée quand les suggestions sont à égalité, accepte le choix 1…9", async () => {
    const user = userEvent.setup();
    render(<Workspace {...props} />);
    await ready();
    region().focus();
    await user.keyboard("j");
    await screen.findByText("BQ-21");
    await user.keyboard("{Enter}");
    expect(window.showToast).toHaveBeenCalledWith("info", expect.stringContaining("équivalentes"));
    expect(calls.some((c) => c.url === "/api/v1/reconciliations")).toBe(false);

    await user.keyboard("2");
    await waitFor(() => expect(calls.find((c) => c.url === "/api/v1/reconciliations")?.body)
      .toEqual({ items: [{ bank_transaction_id: 2, journal_line_id: 22 }] }));
  });

  it("sélectionne une plage et rapproche en masse avec résultat partiel, puis annule", async () => {
    server.reconcileFails.add(3);
    const user = userEvent.setup();
    render(<Workspace {...props} />);
    await ready();
    region().focus();
    await user.keyboard("{Shift>}{ArrowDown}{ArrowDown}{/Shift}");
    expect(screen.getByText("3 sélectionnées :")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Rapprocher les suggestions ★" }));
    await waitFor(() => expect(rows()).toHaveLength(2));
    const post = calls.find((c) => c.url === "/api/v1/reconciliations")!;
    // 2 ignorée (égalité), 1 et 3 envoyées, 3 refusée par le serveur
    expect(post.body.items.map((i: any) => i.bank_transaction_id)).toEqual([1, 3]);
    expect(window.showToast).toHaveBeenCalledWith("info", expect.stringContaining("1 transaction ignorée"));
    expect(window.showToast).toHaveBeenCalledWith("warning", "Montant différent de celui de la transaction.");

    await user.keyboard("{Control>}z{/Control}");
    await waitFor(() => expect(rows()).toHaveLength(3));
    expect(calls.some((c) => c.url === "/api/v1/reconciliations/delete")).toBe(true);
    expect(window.showToast).toHaveBeenCalledWith("success", "Action annulée.");
  });

  it("ouvre le panneau de saisie avec N, prérempli avec la ligne banque", async () => {
    const user = userEvent.setup();
    render(<Workspace {...props} />);
    await ready();
    region().focus();
    await user.keyboard("n");
    const dialog = await screen.findByRole("dialog", { name: "Créer l'écriture" });
    expect(within(dialog).getByLabelText("Compte, ligne 1")).toHaveValue("5121 — CA");
    expect(within(dialog).getByLabelText("Crédit, ligne 1")).toHaveValue("1,00");
    expect(within(dialog).getByLabelText("Journal")).toHaveValue("2");
    await waitFor(() => expect(within(dialog).getByLabelText("Compte, ligne 2")).toHaveFocus());

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("met l'URL à jour avec le compte et le mois", async () => {
    const user = userEvent.setup();
    render(<Workspace {...props} />);
    await ready();
    await user.selectOptions(screen.getByLabelText("Mois"), "2026-03");
    await waitFor(() => expect(window.location.search).toBe("?bank_account_id=1&month=2026-03"));
    expect(calls.some((c) => c.url.includes("month=2026-03"))).toBe(true);
  });

  it("annonce la transaction active aux lecteurs d'écran", async () => {
    const user = userEvent.setup();
    const { container } = render(<Workspace {...props} />);
    await ready();
    const live = () => container.querySelector('.visually-hidden[aria-live="polite"]')!;
    await waitFor(() => expect(live()).toHaveTextContent("Transaction 10/03/2026, PRLV EDF"));
    expect(live()).toHaveTextContent("1 suggestion");
    region().focus();
    await user.keyboard("j");
    await waitFor(() => expect(live()).toHaveTextContent("CB LEROY"));
    await user.keyboard(" ");
    expect(live()).toHaveTextContent("sélectionnée");
    expect(rows()[1]).toHaveAttribute("aria-current", "true");
  });

  it("garde le focus dans le panneau de saisie", async () => {
    const user = userEvent.setup();
    render(<Workspace {...props} />);
    await ready();
    region().focus();
    await user.keyboard("n");
    const dialog = await screen.findByRole("dialog", { name: "Créer l'écriture" });
    const close = within(dialog).getByRole("button", { name: "Fermer (Échap)" });
    close.focus();
    await user.keyboard("{Shift>}{Tab}{/Shift}");
    expect(dialog.contains(document.activeElement)).toBe(true);
    for (let i = 0; i < 40; i++) await user.keyboard("{Tab}");
    expect(dialog.contains(document.activeElement)).toBe(true);
  });
});
