// Saisie d'une écriture (Mantine) : même logique et mêmes raccourcis que l'îlot EntryForm
// (entryState.ts), validation serveur à blanc 400 ms après la dernière modification.
import { useEffect, useMemo, useReducer, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import {
  ActionIcon, Alert, Anchor, Button, Group, Kbd, List, Paper, Select, Stack, Table, Text, TextInput,
  VisuallyHidden,
} from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { notifications } from "@mantine/notifications";
import { X } from "lucide-react";
import { api, ApiError } from "../../api/client";
import { AccountSelect, rememberAccount } from "../../components/AccountSelect";
import { formatEuros, formatDate } from "../../lib/format";
import { toInput } from "../../lib/money";
import type { EntryResponse, FieldErrors } from "../../lib/types";
import {
  balancingAmount, balancingLine, computeTotals, isComplete, isEmptyLine, newLine, reducer,
  toPayload, withMinimumLines, type EntryState, type InitialLine,
} from "./entryState";

const VALIDATE_DELAY_MS = 400;

export interface EntryFormData {
  mode: "create" | "edit";
  entry_id?: number;
  reference?: string;
  options: {
    fiscalYears: { id: number; label: string; start_date: string; end_date: string }[];
    journals: { id: number; code: string; label: string }[];
    recentsScope: string;
    projects?: { value: string; label: string }[];
  };
  initial: { fiscal_year_id: number | null; journal_id: number | null; entry_date: string;
    description: string; lines: InitialLine[] };
  bank_transaction?: { id: number; date: string; label: string; amount_cents: number; return_url: string };
}

type Column = "debit" | "credit";
type FocusTarget = { key: number; field: "account" | Column } | { field: "description" };

function initialState(data: EntryFormData): EntryState {
  return {
    fiscalYearId: data.initial.fiscal_year_id, journalId: data.initial.journal_id,
    date: data.initial.entry_date, description: data.initial.description,
    lines: withMinimumLines(data.initial.lines.map((l) => newLine(l))),
  };
}

function Shortcut({ keys, children }: { keys: string[]; children: ReactNode }) {
  return <List.Item>{keys.map((k, i) => <span key={k}>{i > 0 && " + "}<Kbd size="xs">{k}</Kbd></span>)} : {children}</List.Item>;
}

export function EntryEditor({ data, onSaved, onCancel, focusAccountOfLine }: {
  data: EntryFormData;
  /** Ligne dont le compte reçoit le focus à l'ouverture (ex. 1 : contrepartie d'une transaction). */
  focusAccountOfLine?: number;
  /** Après enregistrement : `after` = "continue" (saisie suivante) ou "open". */
  onSaved: (entry: EntryResponse, after: "open" | "continue") => void;
  onCancel: () => void;
}) {
  const { mode, options, bank_transaction: bankTransaction } = data;
  const [state, dispatch] = useReducer(reducer, data, initialState);
  const [serverErrors, setServerErrors] = useState<FieldErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [pendingFocus, setPendingFocus] = useState<FocusTarget | null>(() => {
    const line = focusAccountOfLine === undefined ? undefined : state.lines[focusAccountOfLine];
    return line ? { key: line.key, field: "account" } : null;
  });
  const fields = useRef(new Map<string, HTMLInputElement | null>());
  const descriptionRef = useRef<HTMLInputElement>(null);

  const totals = useMemo(() => computeTotals(state.lines), [state.lines]);
  const fiscalYear = options.fiscalYears.find((f) => f.id === state.fiscalYearId);
  // Colonne « Projet » seulement si l'instance a des projets (ou si l'écriture en porte).
  const withProjects = (options.projects?.length ?? 0) > 0;
  const dateOutside = !!(fiscalYear && state.date && (state.date < fiscalYear.start_date || state.date > fiscalYear.end_date));
  const filledLines = state.lines.filter((l) => !isEmptyLine(l));

  const blockers: string[] = [];
  if (!state.fiscalYearId) blockers.push("Choisir un exercice.");
  if (!state.journalId) blockers.push("Choisir un journal.");
  if (!state.date) blockers.push("Saisir la date.");
  if (dateOutside) blockers.push("La date est hors de l'exercice.");
  if (totals.invalidAmounts.length) blockers.push("Un montant est mal saisi.");
  if (filledLines.some((l) => !l.account)) blockers.push("Chaque ligne doit avoir un compte.");
  if (filledLines.length < 2) blockers.push("Saisir au moins deux lignes.");
  if (totals.gap !== 0) blockers.push(`Écriture déséquilibrée (écart de ${formatEuros(Math.abs(totals.gap))}).`);
  else if (totals.debit === 0 && filledLines.length >= 2) blockers.push("Le total ne peut pas être nul.");
  if (Object.keys(serverErrors).length) blockers.push("Corriger les erreurs signalées.");
  const canSubmit = blockers.length === 0 && !submitting;

  // Validation serveur (fait foi), 400 ms après la dernière modification.
  const payloadJson = JSON.stringify(toPayload(state));
  useEffect(() => {
    setServerErrors({});
    if (!isComplete(state) || totals.invalidAmounts.length) return;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const res = await api.post<{ errors: FieldErrors }>("/api/v1/entries/validate", JSON.parse(payloadJson),
          { signal: controller.signal });
        setServerErrors(res.errors);
      } catch { /* validation définitive à l'enregistrement */ }
    }, VALIDATE_DELAY_MS);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [payloadJson]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!pendingFocus) return;
    const el = pendingFocus.field === "description" ? descriptionRef.current
      : fields.current.get(`${pendingFocus.key}:${pendingFocus.field}`);
    el?.focus();
    setPendingFocus(null);
  }, [pendingFocus, state.lines]);

  const fieldRef = (key: number, field: string) => (el: HTMLInputElement | null) => { fields.current.set(`${key}:${field}`, el); };

  function addBalancingLine() {
    const line = balancingLine(state.lines, state.description);
    dispatch({ type: "addLine", line });
    setPendingFocus({ key: line.key, field: "account" });
  }

  async function submit(after: "open" | "continue") {
    if (!canSubmit) {
      if (blockers.length) notifications.show({ color: "paille", message: blockers[0] });
      return;
    }
    setSubmitting(true);
    try {
      const payload = toPayload(state, bankTransaction?.id);
      const entry = mode === "edit"
        ? await api.put<EntryResponse>(`/api/v1/entries/${data.entry_id}`, payload)
        : await api.post<EntryResponse>("/api/v1/entries", payload);
      state.lines.forEach((l) => l.account && rememberAccount(options.recentsScope, l.account));
      if (after === "continue" && mode === "create" && !bankTransaction) {
        notifications.show({ color: "lichen", message: `Écriture ${entry.reference} enregistrée.` });
        dispatch({ type: "reset" });
        setPendingFocus({ field: "description" });
      }
      onSaved(entry, after);
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) setServerErrors(err.fields);
      notifications.show({ color: "brique", message: err instanceof Error ? err.message : "Erreur inattendue." });
    }
    setSubmitting(false);
  }

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const target = e.target as HTMLElement;
    const lineIndex = target.dataset.line !== undefined ? Number(target.dataset.line) : -1;
    const field = target.dataset.field;
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      void submit(e.shiftKey || mode === "edit" ? "open" : "continue");
      return;
    }
    if (e.key === "Enter" && target.tagName === "INPUT") {
      e.preventDefault();
      if ((field === "debit" || field === "credit") && lineIndex === state.lines.length - 1) addBalancingLine();
      else if (field === "description") setPendingFocus({ key: state.lines[0].key, field: "account" });
      return;
    }
    if (e.key === "Delete" && e.ctrlKey && lineIndex >= 0) {
      e.preventDefault();
      const previous = state.lines[Math.max(lineIndex - 1, 0)];
      dispatch({ type: "removeLine", index: lineIndex });
      if (previous && previous !== state.lines[lineIndex]) setPendingFocus({ key: previous.key, field: "account" });
    }
  }

  function onAmountKeyDown(e: KeyboardEvent<HTMLInputElement>, index: number, column: Column) {
    if (e.key === "=") {
      e.preventDefault();
      const other: Column = column === "debit" ? "credit" : "debit";
      dispatch({ type: "line", index, patch: { [column]: toInput(balancingAmount(state.lines, index, column)), [other]: "" } });
    }
  }

  const err = (name: string) => serverErrors[name];
  const balanced = totals.gap === 0 && totals.debit > 0;

  return (
    <div onKeyDown={onKeyDown}>
      {bankTransaction && (
        <Alert color="ardoise" variant="light" mb="md" role="status">
          Depuis la transaction du <b>{formatDate(bankTransaction.date)}</b> — {bankTransaction.label || "(sans libellé)"} —{" "}
          <b className="lv-num">{formatEuros(bankTransaction.amount_cents)}</b>. Complétez la contrepartie : à
          l'enregistrement, la transaction sera rapprochée.
        </Alert>
      )}
      <form noValidate onSubmit={(e) => { e.preventDefault(); void submit("open"); }}>
        <Stack gap="md">
          <Group grow align="flex-start">
            <Select label="Exercice" data={options.fiscalYears.map((f) => ({ value: String(f.id), label: f.label }))}
              value={state.fiscalYearId ? String(state.fiscalYearId) : null} error={err("fiscal_year_id")}
              onChange={(v) => dispatch({ type: "field", field: "fiscalYearId", value: v ? Number(v) : null })} />
            <Select label="Journal" data={options.journals.map((j) => ({ value: String(j.id), label: `${j.code} — ${j.label}` }))}
              value={state.journalId ? String(state.journalId) : null} error={err("journal_id")}
              onChange={(v) => dispatch({ type: "field", field: "journalId", value: v ? Number(v) : null })} />
            <DateInput label="Date" valueFormat="DD/MM/YYYY" value={state.date || null}
              error={err("entry_date") ?? (dateOutside && fiscalYear ? `Hors de l'exercice ${fiscalYear.label}.` : undefined)}
              onChange={(v) => dispatch({ type: "field", field: "date", value: v ?? "" })} />
          </Group>
          <TextInput ref={descriptionRef} label="Description" placeholder="Libellé de l'écriture" data-field="description"
            value={state.description} onChange={(e) => dispatch({ type: "field", field: "description", value: e.currentTarget.value })} />

          <Paper p={0} style={{ overflowX: "auto" }}>
            <Table verticalSpacing={6} style={{ minWidth: 760 }}>
              <Table.Thead bg="var(--lv-sauge)">
                <Table.Tr>
                  <Table.Th w="34%">Compte</Table.Th><Table.Th w="30%">Libellé</Table.Th>
                  {withProjects && <Table.Th w="16%">Projet</Table.Th>}
                  <Table.Th w="15%" ta="right">Débit</Table.Th><Table.Th w="15%" ta="right">Crédit</Table.Th>
                  <Table.Th w="6%"><VisuallyHidden>Actions</VisuallyHidden></Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {state.lines.map((line, i) => {
                  const badAmount = totals.invalidAmounts.includes(i);
                  const amountError = err(`lines[${i}].amount`) ?? (badAmount ? "Montant invalide." : undefined);
                  return (
                    <Table.Tr key={line.key} style={{ verticalAlign: "top" }}>
                      <Table.Td>
                        <AccountSelect ref={fieldRef(line.key, "account")} value={line.account} line={i}
                          label={`Compte, ligne ${i + 1}`} recentsScope={options.recentsScope}
                          error={err(`lines[${i}].account_id`)}
                          onChange={(account) => dispatch({ type: "line", index: i, patch: { account } })} />
                      </Table.Td>
                      <Table.Td>
                        <TextInput aria-label={`Libellé, ligne ${i + 1}`} placeholder={state.description} data-line={i}
                          data-field="label" value={line.label}
                          onChange={(e) => dispatch({ type: "line", index: i, patch: { label: e.currentTarget.value } })} />
                      </Table.Td>
                      {withProjects && (
                        <Table.Td>
                          <Select aria-label={`Projet, ligne ${i + 1}`} data={options.projects} value={line.projectId} clearable
                            searchable placeholder="—" data-line={i} data-field="project" error={err(`lines[${i}].project_id`)}
                            onChange={(projectId) => dispatch({ type: "line", index: i, patch: { projectId } })} />
                        </Table.Td>
                      )}
                      {(["debit", "credit"] as Column[]).map((column) => (
                        <Table.Td key={column}>
                          <TextInput ref={fieldRef(line.key, column)} inputMode="decimal" data-line={i} data-field={column}
                            aria-label={`${column === "debit" ? "Débit" : "Crédit"}, ligne ${i + 1}`}
                            classNames={{ input: "lv-num" }} styles={{ input: { textAlign: "right" } }}
                            error={column === "credit" ? amountError : amountError ? " " : undefined}
                            value={line[column]} onKeyDown={(e) => onAmountKeyDown(e, i, column)}
                            onChange={(e) => dispatch({ type: "line", index: i, patch: { [column]: e.currentTarget.value } })} />
                        </Table.Td>
                      ))}
                      <Table.Td ta="right">
                        <ActionIcon variant="subtle" color="brique" tabIndex={-1} size={44}
                          title="Supprimer la ligne (Ctrl+Suppr)" aria-label={`Supprimer la ligne ${i + 1}`}
                          onClick={() => dispatch({ type: "removeLine", index: i })}><X size={18} /></ActionIcon>
                      </Table.Td>
                    </Table.Tr>
                  );
                })}
              </Table.Tbody>
              <Table.Tfoot>
                <Table.Tr>
                  <Table.Td colSpan={withProjects ? 3 : 2}><Button variant="default" size="compact-md" onClick={addBalancingLine}>Ajouter une ligne</Button></Table.Td>
                  <Table.Td ta="right" className="lv-num" fw={600}>{formatEuros(totals.debit)}</Table.Td>
                  <Table.Td ta="right" className="lv-num" fw={600}>{formatEuros(totals.credit)}</Table.Td>
                  <Table.Td />
                </Table.Tr>
              </Table.Tfoot>
            </Table>
          </Paper>

          <Group gap="sm">
            <Button type="submit" disabled={!canSubmit} loading={submitting} title="Ctrl+Maj+Entrée">Enregistrer</Button>
            {mode === "create" && !bankTransaction && (
              <Button variant="default" disabled={!canSubmit} title="Ctrl+Entrée" onClick={() => void submit("continue")}>
                Enregistrer et saisir la suivante</Button>
            )}
            <Button variant="subtle" onClick={onCancel}>Annuler</Button>
            <Text ml="auto" size="sm" role="status" aria-live="polite" className="lv-num"
              c={totals.gap === 0 ? "var(--lv-lichen)" : "var(--lv-brique)"}>
              {totals.gap === 0 ? (balanced ? `Équilibrée : ${formatEuros(totals.debit)}` : "")
                : `Écart : ${formatEuros(Math.abs(totals.gap))}`}
            </Text>
          </Group>
          {err("lines") && <Text c="var(--lv-brique)" size="sm" role="alert">{err("lines")}</Text>}
        </Stack>
      </form>
      <details style={{ marginTop: 16 }}>
        <summary><Anchor component="span" size="sm">Raccourcis clavier</Anchor></summary>
        <List size="sm" c="dimmed" mt={4}>
          <Shortcut keys={["Entrée"]}>dans un montant de la dernière ligne, nouvelle ligne préremplie avec l'écart</Shortcut>
          <Shortcut keys={["="]}>dans un montant, montant qui équilibre l'écriture</Shortcut>
          <Shortcut keys={["Alt", "↓"]}>ouvrir la liste des comptes ; Échap la ferme</Shortcut>
          <Shortcut keys={["Ctrl", "Suppr"]}>supprimer la ligne</Shortcut>
          {mode === "create" && <Shortcut keys={["Ctrl", "Entrée"]}>enregistrer et saisir la suivante</Shortcut>}
          <Shortcut keys={["Ctrl", "Maj", "Entrée"]}>enregistrer et ouvrir l'écriture</Shortcut>
        </List>
      </details>
    </div>
  );
}
