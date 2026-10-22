import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { SESSION_KEY, type Session } from "../api/session";
import { renderWithProviders, TEST_SESSION } from "../test/render";
import { ConfirmButton } from "./ConfirmButton";
import { DataGrid, formatSort, parseSort, type GridColumn } from "./DataGrid";
import { MoneyInput, MoneyText } from "./Money";

interface Row { id: number; code: string; label: string }

const ROWS: Row[] = [
  { id: 1, code: "VT", label: "Ventes" },
  { id: 2, code: "AC", label: "Achats" },
  { id: 3, code: "BQ", label: "Banque" },
];
const COLUMNS: GridColumn<Row>[] = [
  { accessor: "code", title: "Code", sortable: true, hideable: false },
  { accessor: "label", title: "Libellé", sortable: true },
];

function codes() {
  return screen.getAllByRole("row").slice(1).map((row) => within(row).getAllByRole("cell")[0].textContent);
}

afterEach(() => vi.restoreAllMocks());

describe("DataGrid", () => {
  it("trie localement au clic sur l'en-tête", async () => {
    renderWithProviders(<DataGrid id="journals" records={ROWS} columns={COLUMNS}
      defaultSort={{ column: "code", direction: "asc" }} />);
    expect(codes()).toEqual(["AC", "BQ", "VT"]);
    await userEvent.click(screen.getByText("Libellé"));
    expect(codes()).toEqual(["AC", "BQ", "VT"]); // Achats, Banque, Ventes
    await userEvent.click(screen.getByText("Code"));
    await userEvent.click(screen.getByText("Code"));
    expect(codes()).toEqual(["VT", "BQ", "AC"]);
    expect(screen.getByText("3 élément(s)")).toBeInTheDocument();
  });

  it("masque une colonne et mémorise le choix dans les préférences", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ preferences: {} }), { status: 200 }));
    const { client } = renderWithProviders(<DataGrid id="journals" records={ROWS} columns={COLUMNS} />);
    expect(screen.getByText("Ventes")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Colonnes affichées" }));
    await userEvent.click(await screen.findByText("Libellé", { selector: "label" }));
    await waitFor(() => expect(screen.queryByText("Ventes")).not.toBeInTheDocument());
    expect(client.getQueryData<Session>(SESSION_KEY)?.preferences.tables?.journals.hidden).toEqual(["label"]);
    await vi.advanceTimersByTimeAsync(600);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/me/preferences");
    expect(JSON.parse(String(init?.body))).toEqual({ tables: { journals: { hidden: ["label"] } } });
    vi.useRealTimers();
  });

  it("applique les colonnes masquées de la session", () => {
    const session = { ...TEST_SESSION, preferences: { tables: { journals: { hidden: ["label"] } } } };
    renderWithProviders(<DataGrid id="journals" records={ROWS} columns={COLUMNS} />, { session });
    expect(screen.queryByText("Ventes")).not.toBeInTheDocument();
  });

  it("affiche la sélection et ses actions", async () => {
    function Selectable() {
      const [selected, setSelected] = useState<Row[]>([]);
      return <DataGrid id="t" records={ROWS} columns={COLUMNS}
        selection={{ selected, onChange: setSelected, actions: (rows) => <span>action sur {rows.length}</span> }} />;
    }
    renderWithProviders(<Selectable />);
    await userEvent.click(screen.getAllByRole("checkbox")[1]);
    expect(screen.getByText("1 sélectionné(s)")).toBeInTheDocument();
    expect(screen.getByText("action sur 1")).toBeInTheDocument();
  });

  it("paramètre de tri de l'API", () => {
    expect(parseSort("-date")).toEqual({ column: "date", direction: "desc" });
    expect(parseSort("code")).toEqual({ column: "code", direction: "asc" });
    expect(parseSort("")).toBeNull();
    expect(formatSort({ column: "date", direction: "desc" })).toBe("-date");
  });
});

describe("Money", () => {
  it("saisit des euros et renvoie des centimes", async () => {
    const onChange = vi.fn();
    renderWithProviders(<MoneyInput label="Montant" value={null} onChange={onChange} />);
    await userEvent.type(screen.getByLabelText("Montant"), "1234,5");
    expect(onChange).toHaveBeenLastCalledWith(123450);
  });

  it("affiche un montant au format français", () => {
    renderWithProviders(<MoneyText cents={123456} />);
    expect(screen.getByText(/1\s234,56\s€/)).toBeInTheDocument();
  });

  it("utilise le signe moins typographique, sans rouge par défaut", () => {
    renderWithProviders(<><MoneyText cents={-124800} /><MoneyText cents={500} plus /></>);
    const debit = screen.getByText(/1\s248,00/);
    expect(debit.textContent!.startsWith("\u2212")).toBe(true);
    expect(debit).not.toHaveStyle({ color: "var(--lv-brique)" });
    expect(screen.getByText(/^\+5,00/)).toBeInTheDocument();
  });
});

describe("ConfirmButton", () => {
  it("demande confirmation avant d'agir", async () => {
    const onConfirm = vi.fn();
    renderWithProviders(<ConfirmButton title="Supprimer le journal VT ?" onConfirm={onConfirm}>Supprimer</ConfirmButton>);
    await userEvent.click(screen.getByRole("button", { name: "Supprimer" }));
    expect(await screen.findByRole("dialog", { name: "Supprimer le journal VT ?" })).toBeInTheDocument();
    expect(onConfirm).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Confirmer" }));
    expect(onConfirm).toHaveBeenCalledOnce();
  });
});
