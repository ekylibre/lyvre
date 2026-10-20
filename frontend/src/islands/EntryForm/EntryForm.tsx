import {
  useEffect, useMemo, useReducer, useRef, useState, type KeyboardEvent, type ReactNode,
} from "react";
import { AccountCombobox, rememberAccount } from "../../components/AccountCombobox";
import { api, ApiError } from "../../lib/api";
import { formatEuros, toInput } from "../../lib/money";
import { toast } from "../../lib/toast";
import type { EntryResponse, FieldErrors } from "../../lib/types";
import {
  balancingAmount, balancingLine, computeTotals, isComplete, isEmptyLine, newLine, reducer,
  toPayload, withMinimumLines, type EntryState, type InitialLine,
} from "./entryState";

const VALIDATE_DELAY_MS = 400;

export interface FiscalYearOption {
  id: number;
  label: string;
  start_date: string;
  end_date: string;
}

export interface JournalOption {
  id: number;
  code: string;
  label: string;
}

export interface BankTransactionInfo {
  id: number;
  date: string;
  label: string;
  amount_cents: number;
}

export interface EntryFormProps {
  mode: "create" | "edit";
  entryId?: number;
  reference?: string;
  fiscalYears: FiscalYearOption[];
  journals: JournalOption[];
  initial: {
    fiscal_year_id: number | null;
    journal_id: number | null;
    entry_date: string;
    description: string;
    lines: InitialLine[];
  };
  bankTransaction?: BankTransactionInfo;
  urls: { api: string; cancel: string; afterSave?: string };
  /** Clé des comptes récents (une liste par instance). */
  recentsScope: string;
  /** Intégration dans un autre îlot : appelé à la place de la navigation. */
  onSaved?: (entry: EntryResponse) => void;
  /** Intégration : bouton Annuler sans navigation. */
  onCancel?: () => void;
}

type Column = "debit" | "credit";
type FocusTarget = { key: number; field: "account" | Column } | { field: "description" };

function initialState(p: EntryFormProps): EntryState {
  return {
    fiscalYearId: p.initial.fiscal_year_id,
    journalId: p.initial.journal_id,
    date: p.initial.entry_date,
    description: p.initial.description,
    lines: withMinimumLines(p.initial.lines.map((l) => newLine(l))),
  };
}

function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return <div id={id} className="invalid-feedback d-block">{message}</div>;
}

function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="bg-light text-dark border">{children}</kbd>;
}

export default function EntryForm(props: EntryFormProps) {
  const { mode, fiscalYears, journals, bankTransaction, urls } = props;
  const [state, dispatch] = useReducer(reducer, props, initialState);
  const [serverErrors, setServerErrors] = useState<FieldErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [pendingFocus, setPendingFocus] = useState<FocusTarget | null>(null);
  const fields = useRef(new Map<string, HTMLInputElement | null>());
  const descriptionRef = useRef<HTMLInputElement>(null);

  const totals = useMemo(() => computeTotals(state.lines), [state.lines]);
  const fiscalYear = fiscalYears.find((f) => f.id === state.fiscalYearId);
  const dateOutside = !!(fiscalYear && state.date &&
    (state.date < fiscalYear.start_date || state.date > fiscalYear.end_date));
  const filledLines = state.lines.filter((l) => !isEmptyLine(l));
  const missingAccount = filledLines.some((l) => !l.account);

  const blockers: string[] = [];
  if (!state.fiscalYearId) blockers.push("Choisir un exercice.");
  if (!state.journalId) blockers.push("Choisir un journal.");
  if (!state.date) blockers.push("Saisir la date.");
  if (dateOutside) blockers.push("La date est hors de l'exercice.");
  if (totals.invalidAmounts.length) blockers.push("Un montant est mal saisi.");
  if (missingAccount) blockers.push("Chaque ligne doit avoir un compte.");
  if (filledLines.length < 2) blockers.push("Saisir au moins deux lignes.");
  if (totals.gap !== 0) blockers.push(`Écriture déséquilibrée (écart de ${formatEuros(Math.abs(totals.gap))}).`);
  else if (totals.debit === 0 && filledLines.length >= 2) blockers.push("Le total ne peut pas être nul.");
  if (Object.keys(serverErrors).length) blockers.push("Corriger les erreurs signalées.");
  const canSubmit = blockers.length === 0 && !submitting;

  // --- validation serveur (fait foi), 400 ms après la dernière modification ---
  const payloadJson = JSON.stringify(toPayload(state));
  useEffect(() => {
    setServerErrors({});
    if (!isComplete(state) || totals.invalidAmounts.length) return;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const res = await api<{ errors: FieldErrors }>(
          "POST", `${urls.api}/entries/validate`, JSON.parse(payloadJson), controller.signal);
        setServerErrors(res.errors);
      } catch {
        /* la validation définitive a lieu à l'enregistrement */
      }
    }, VALIDATE_DELAY_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [payloadJson]); // payloadJson résume tout l'état envoyé au serveur

  // --- focus après ajout / réinitialisation --------------------------------
  useEffect(() => {
    if (!pendingFocus) return;
    const el = pendingFocus.field === "description"
      ? descriptionRef.current
      : fields.current.get(`${pendingFocus.key}:${pendingFocus.field}`);
    el?.focus();
    setPendingFocus(null);
  }, [pendingFocus, state.lines]);

  function fieldRef(key: number, field: string) {
    return (el: HTMLInputElement | null) => {
      fields.current.set(`${key}:${field}`, el);
    };
  }

  function addBalancingLine() {
    const line = balancingLine(state.lines, state.description);
    dispatch({ type: "addLine", line });
    setPendingFocus({ key: line.key, field: "account" });
  }

  async function submit(after: "open" | "continue") {
    if (!canSubmit) {
      if (blockers.length) toast("warning", blockers[0]);
      return;
    }
    setSubmitting(true);
    try {
      const payload = toPayload(state, bankTransaction?.id);
      const entry = mode === "edit"
        ? await api<EntryResponse>("PUT", `${urls.api}/entries/${props.entryId}`, payload)
        : await api<EntryResponse>("POST", `${urls.api}/entries`, payload);
      state.lines.forEach((l) => l.account && rememberAccount(props.recentsScope, l.account));

      if (props.onSaved) {
        props.onSaved(entry);
      } else if (after === "continue" && mode === "create" && !bankTransaction) {
        toast("success", `Écriture ${entry.reference} enregistrée.`);
        dispatch({ type: "reset" });
        setPendingFocus({ field: "description" });
      } else {
        window.location.assign(urls.afterSave ?? entry.url);
        return; // la page change : garder le bouton désactivé
      }
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 422) setServerErrors(err.fields);
        toast("danger", err.message);
      } else {
        toast("danger", "Erreur inattendue lors de l'enregistrement.");
      }
    }
    setSubmitting(false);
  }

  // --- clavier --------------------------------------------------------------
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
      e.preventDefault(); // pas d'envoi implicite du formulaire
      if ((field === "debit" || field === "credit") && lineIndex === state.lines.length - 1) {
        addBalancingLine();
      } else if (field === "description") {
        setPendingFocus({ key: state.lines[0].key, field: "account" });
      }
      return;
    }
    if (e.key === "Delete" && e.ctrlKey && lineIndex >= 0) {
      e.preventDefault();
      const previous = state.lines[Math.max(lineIndex - 1, 0)];
      dispatch({ type: "removeLine", index: lineIndex });
      if (previous && previous !== state.lines[lineIndex]) {
        setPendingFocus({ key: previous.key, field: "account" });
      }
    }
  }

  function onAmountKeyDown(e: KeyboardEvent<HTMLInputElement>, index: number, column: Column) {
    if (e.key === "=") {
      e.preventDefault();
      const amount = balancingAmount(state.lines, index, column);
      const other: Column = column === "debit" ? "credit" : "debit";
      dispatch({ type: "line", index, patch: { [column]: toInput(amount), [other]: "" } });
    }
  }

  const err = (name: string) => serverErrors[name];
  const errId = (name: string) => `entry-err-${name.replace(/[^a-z0-9]/gi, "-")}`;
  const described = (name: string) => (err(name) ? errId(name) : undefined);

  return (
    <div onKeyDown={onKeyDown}>
      {bankTransaction && (
        <div className="alert alert-info py-2 small">
          Depuis la transaction du <strong>{bankTransaction.date.split("-").reverse().join("/")}</strong>
          {" — "}{bankTransaction.label || "(sans libellé)"}{" — "}
          <span className={`font-monospace ${bankTransaction.amount_cents < 0 ? "text-danger" : "text-success"}`}>
            {formatEuros(bankTransaction.amount_cents)}
          </span>
          . Complétez la contrepartie : à l'enregistrement, la transaction sera rapprochée.
        </div>
      )}

      <form noValidate onSubmit={(e) => { e.preventDefault(); void submit("open"); }}>
        <div className="row g-3 mb-3">
          <div className="col-md-3">
            <label className="form-label" htmlFor="entry-fy">Exercice</label>
            <select id="entry-fy" className={`form-select form-select-sm${err("fiscal_year_id") ? " is-invalid" : ""}`}
                    value={state.fiscalYearId ?? ""} aria-describedby={described("fiscal_year_id")}
                    onChange={(e) => dispatch({ type: "field", field: "fiscalYearId", value: Number(e.target.value) || null })}>
              <option value="">— Exercice —</option>
              {fiscalYears.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}
            </select>
            <FieldError id={errId("fiscal_year_id")} message={err("fiscal_year_id")} />
          </div>
          <div className="col-md-3">
            <label className="form-label" htmlFor="entry-journal">Journal</label>
            <select id="entry-journal" className={`form-select form-select-sm${err("journal_id") ? " is-invalid" : ""}`}
                    value={state.journalId ?? ""} aria-describedby={described("journal_id")}
                    onChange={(e) => dispatch({ type: "field", field: "journalId", value: Number(e.target.value) || null })}>
              <option value="">— Journal —</option>
              {journals.map((j) => <option key={j.id} value={j.id}>{j.code} — {j.label}</option>)}
            </select>
            <FieldError id={errId("journal_id")} message={err("journal_id")} />
          </div>
          <div className="col-md-3">
            <label className="form-label" htmlFor="entry-date">Date</label>
            <input id="entry-date" type="date"
                   className={`form-control form-control-sm${err("entry_date") || dateOutside ? " is-invalid" : ""}`}
                   value={state.date} aria-describedby={described("entry_date") ?? (dateOutside ? "entry-date-hint" : undefined)}
                   onChange={(e) => dispatch({ type: "field", field: "date", value: e.target.value })} />
            <FieldError id={errId("entry_date")} message={err("entry_date")} />
            {!err("entry_date") && dateOutside && fiscalYear && (
              <div id="entry-date-hint" className="invalid-feedback d-block">
                Hors de l'exercice {fiscalYear.label}.
              </div>
            )}
          </div>
          <div className="col-md-9">
            <label className="form-label" htmlFor="entry-description">Description</label>
            <input id="entry-description" ref={descriptionRef} type="text" data-field="description"
                   className="form-control form-control-sm" placeholder="Libellé de l'écriture"
                   value={state.description}
                   onChange={(e) => dispatch({ type: "field", field: "description", value: e.target.value })} />
          </div>
        </div>

        <table className="table table-sm align-top mb-1">
          <thead className="table-light">
            <tr>
              <th style={{ width: "34%" }}>Compte</th>
              <th style={{ width: "30%" }}>Libellé</th>
              <th style={{ width: "15%" }} className="text-end">Débit (€)</th>
              <th style={{ width: "15%" }} className="text-end">Crédit (€)</th>
              <th style={{ width: "6%" }}><span className="visually-hidden">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {state.lines.map((line, i) => {
              const accountErr = `lines[${i}].account_id`;
              const amountErr = `lines[${i}].amount`;
              const badAmount = totals.invalidAmounts.includes(i);
              return (
                <tr key={line.key}>
                  <td>
                    <AccountCombobox
                      ref={fieldRef(line.key, "account")}
                      value={line.account}
                      onChange={(account) => dispatch({ type: "line", index: i, patch: { account } })}
                      searchUrl={`${urls.api}/accounts`}
                      recentsScope={props.recentsScope}
                      label={`Compte, ligne ${i + 1}`}
                      line={i}
                      invalid={!!err(accountErr)}
                      describedBy={described(accountErr)}
                    />
                    <FieldError id={errId(accountErr)} message={err(accountErr)} />
                  </td>
                  <td>
                    <input type="text" className="form-control form-control-sm" data-line={i} data-field="label"
                           aria-label={`Libellé, ligne ${i + 1}`} placeholder={state.description}
                           value={line.label}
                           onChange={(e) => dispatch({ type: "line", index: i, patch: { label: e.target.value } })} />
                  </td>
                  {(["debit", "credit"] as Column[]).map((column) => (
                    <td key={column}>
                      <input
                        ref={fieldRef(line.key, column)}
                        type="text" inputMode="decimal" data-line={i} data-field={column}
                        className={`form-control form-control-sm text-end font-monospace${badAmount || err(amountErr) ? " is-invalid" : ""}`}
                        aria-label={`${column === "debit" ? "Débit" : "Crédit"}, ligne ${i + 1}`}
                        aria-describedby={described(amountErr)}
                        value={line[column]}
                        onKeyDown={(e) => onAmountKeyDown(e, i, column)}
                        onChange={(e) => dispatch({ type: "line", index: i, patch: { [column]: e.target.value } })}
                      />
                      {column === "credit" && (
                        <FieldError id={errId(amountErr)}
                                    message={err(amountErr) ?? (badAmount ? "Montant invalide." : undefined)} />
                      )}
                    </td>
                  ))}
                  <td className="text-end">
                    <button type="button" className="btn btn-sm btn-outline-danger" tabIndex={-1}
                            title="Supprimer la ligne (Ctrl+Suppr)" aria-label={`Supprimer la ligne ${i + 1}`}
                            onClick={() => dispatch({ type: "removeLine", index: i })}>×</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr className="fw-semibold">
              <td colSpan={2}>
                <button type="button" className="btn btn-sm btn-outline-secondary" onClick={addBalancingLine}>
                  + Ligne
                </button>
              </td>
              <td className="text-end font-monospace">{formatEuros(totals.debit)}</td>
              <td className="text-end font-monospace">{formatEuros(totals.credit)}</td>
              <td />
            </tr>
          </tfoot>
        </table>

        <div className="d-flex flex-wrap align-items-center gap-2 mt-2">
          <button type="submit" className="btn btn-primary btn-sm" disabled={!canSubmit}
                  title="Ctrl+Maj+Entrée">
            {submitting ? "Enregistrement…" : "Enregistrer"}
          </button>
          {mode === "create" && !bankTransaction && (
            <button type="button" className="btn btn-outline-primary btn-sm" disabled={!canSubmit}
                    title="Ctrl+Entrée" onClick={() => void submit("continue")}>
              Enregistrer et nouvelle
            </button>
          )}
          {props.onCancel
            ? <button type="button" className="btn btn-outline-secondary btn-sm" onClick={props.onCancel}>Annuler</button>
            : <a href={urls.cancel} className="btn btn-outline-secondary btn-sm">Annuler</a>}
          <span className={`ms-auto small ${totals.gap === 0 && totals.debit > 0 ? "text-success" : "text-danger"}`}
                role="status" aria-live="polite">
            {totals.gap === 0
              ? (totals.debit > 0 ? `✓ Équilibrée (${formatEuros(totals.debit)})` : "")
              : `Écart : ${formatEuros(Math.abs(totals.gap))}`}
          </span>
        </div>
        {err("lines") && <div className="text-danger small mt-1" role="alert">{err("lines")}</div>}
      </form>

      <details className="small text-muted mt-3">
        <summary>Raccourcis clavier</summary>
        <ul className="mb-0 mt-1">
          <li><Kbd>Tab</Kbd> / <Kbd>Maj</Kbd>+<Kbd>Tab</Kbd> : champ suivant / précédent</li>
          <li><Kbd>Entrée</Kbd> dans un montant de la dernière ligne : nouvelle ligne préremplie avec l'écart</li>
          <li><Kbd>=</Kbd> dans un montant : montant qui équilibre l'écriture</li>
          <li><Kbd>Alt</Kbd>+<Kbd>↓</Kbd> : ouvrir la liste des comptes ; <Kbd>Échap</Kbd> : la fermer</li>
          <li><Kbd>Ctrl</Kbd>+<Kbd>Suppr</Kbd> : supprimer la ligne</li>
          {mode === "create" && <li><Kbd>Ctrl</Kbd>+<Kbd>Entrée</Kbd> : enregistrer et saisir la suivante</li>}
          <li><Kbd>Ctrl</Kbd>+<Kbd>Maj</Kbd>+<Kbd>Entrée</Kbd> : enregistrer et ouvrir l'écriture</li>
        </ul>
      </details>
    </div>
  );
}
