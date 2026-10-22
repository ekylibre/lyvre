import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import EntryForm, { type FiscalYearOption, type JournalOption } from "../EntryForm/EntryForm";
import { api, ApiError } from "../../lib/api";
import { formatEuros } from "../../lib/money";
import { toast } from "../../lib/toast";
import type {
  Account, ApplyRulesResponse, BankTransaction, BatchResponse, Counters, EntryResponse,
  Suggestion, UndoRequest,
} from "../../lib/types";
import { activeAfterRemoval, attachmentBadge, bestSuggestion, plural, rangeIds, REVERSED_MESSAGE } from "./logic";

const UNDO_VISIBLE_MS = 10_000;
const PREFETCH_NEXT = 3;

export interface BankAccountOption {
  id: number;
  label: string;
  account: Account;
}

export interface WorkspaceProps {
  bankAccounts: BankAccountOption[];
  bankAccountId: number | null;
  month: string;
  monthOptions: { value: string; label: string }[];
  urls: { api: string; page: string };
  entryForm: {
    fiscalYears: FiscalYearOption[];
    journals: JournalOption[];
    defaultJournalId: number | null;
    recentsScope: string;
  };
}

interface UndoState {
  message: string;
  request: UndoRequest;
}

function frDate(iso: string) {
  return iso.split("-").reverse().join("/");
}

/** Raccourcis ignorés quand on tape dans un champ (filtres, panneau de saisie). */
function isTyping(target: EventTarget | null) {
  const el = target as HTMLElement | null;
  return !!el && (el.tagName === "INPUT" || el.tagName === "SELECT" || el.tagName === "TEXTAREA");
}

export default function Workspace(props: WorkspaceProps) {
  const { urls, bankAccounts } = props;
  const [bankAccountId, setBankAccountId] = useState<number | null>(
    props.bankAccountId ?? bankAccounts[0]?.id ?? null);
  const [month, setMonth] = useState(props.month);
  const [transactions, setTransactions] = useState<BankTransaction[]>([]);
  const [counters, setCounters] = useState<Counters | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [anchorId, setAnchorId] = useState<number | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [suggestions, setSuggestions] = useState<Map<number, Suggestion[]>>(new Map());
  const [busy, setBusy] = useState(false);
  const [undo, setUndo] = useState<UndoState | null>(null);
  const [panelFor, setPanelFor] = useState<BankTransaction | null>(null);
  const tableRef = useRef<HTMLDivElement>(null);
  const undoTimer = useRef<number | undefined>(undefined);
  const pending = useRef(new Set<number>());

  const ids = useMemo(() => transactions.map((t) => t.id), [transactions]);
  const active = transactions.find((t) => t.id === activeId) ?? null;
  const bankAccount = bankAccounts.find((b) => b.id === bankAccountId) ?? null;

  // --- chargement ------------------------------------------------------------
  const load = useCallback(async () => {
    if (!bankAccountId) return;
    setLoading(true);
    const params = new URLSearchParams({ status: "unreconciled", sort: "asc" });
    if (month) params.set("month", month);
    try {
      const data = await api<{ transactions: BankTransaction[]; counters: Counters }>(
        "GET", `${urls.api}/bank-accounts/${bankAccountId}/transactions?${params}`);
      setTransactions(data.transactions);
      setCounters(data.counters);
      setSelected(new Set());
      setSuggestions(new Map());
      pending.current.clear();
      setActiveId((current) =>
        data.transactions.some((t) => t.id === current) ? current : data.transactions[0]?.id ?? null);
    } catch (err) {
      toast("danger", err instanceof ApiError ? err.message : "Chargement impossible.");
    }
    setLoading(false);
  }, [bankAccountId, month, urls.api]);

  useEffect(() => {
    void load();
    const query = new URLSearchParams();
    if (bankAccountId) query.set("bank_account_id", String(bankAccountId));
    if (month) query.set("month", month);
    window.history.replaceState(null, "", `${urls.page}?${query}`);
  }, [load, bankAccountId, month, urls.page]);

  // --- suggestions : ligne active + préchargement des suivantes ------------
  const loadSuggestions = useCallback(async (btId: number): Promise<Suggestion[] | undefined> => {
    try {
      const data = await api<{ suggestions: Suggestion[] }>(
        "GET", `${urls.api}/bank-transactions/${btId}/suggestions`);
      setSuggestions((m) => new Map(m).set(btId, data.suggestions));
      return data.suggestions;
    } catch {
      return undefined;
    }
  }, [urls.api]);

  const fetchSuggestions = useCallback(async (btId: number) => {
    if (pending.current.has(btId)) return;
    pending.current.add(btId);
    if ((await loadSuggestions(btId)) === undefined) pending.current.delete(btId);
  }, [loadSuggestions]);

  useEffect(() => {
    if (activeId === null) return;
    const start = ids.indexOf(activeId);
    ids.slice(start, start + 1 + PREFETCH_NEXT).forEach((id) => void fetchSuggestions(id));
  }, [activeId, ids, fetchSuggestions]);

  // Ligne active visible quand on navigue au clavier.
  useEffect(() => {
    if (activeId === null) return;
    tableRef.current?.querySelector(`[data-bt="${activeId}"]`)?.scrollIntoView({ block: "nearest" });
  }, [activeId]);

  // --- application des résultats ----------------------------------------------
  function offerUndo(message: string, request: UndoRequest | null) {
    window.clearTimeout(undoTimer.current);
    if (!request) {
      setUndo(null);
      return;
    }
    setUndo({ message, request });
    undoTimer.current = window.setTimeout(() => setUndo(null), UNDO_VISIBLE_MS);
  }

  function removeDone(doneIds: number[], newCounters: Counters | null) {
    const removed = new Set(doneIds);
    setActiveId((current) => activeAfterRemoval(ids, current, removed));
    setTransactions((list) => list.filter((t) => !removed.has(t.id)));
    setSelected((s) => new Set([...s].filter((id) => !removed.has(id))));
    if (newCounters) setCounters(newCounters);
    tableRef.current?.focus();
  }

  function reportErrors(results: BatchResponse["results"]) {
    const failed = results.filter((r) => r.status === "error");
    if (failed.length === 1) toast("warning", failed[0].message ?? "Rapprochement refusé.");
    else if (failed.length > 1) toast("warning", `${plural(failed.length, "transaction non rapprochée", "transactions non rapprochées")} (contrôles de montant / compte).`);
  }

  async function run<T>(action: () => Promise<T>): Promise<T | null> {
    if (busy) return null;
    setBusy(true);
    try {
      return await action();
    } catch (err) {
      toast("danger", err instanceof ApiError ? err.message : "Action impossible.");
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function reconcile(items: { bank_transaction_id: number; journal_line_id: number }[]) {
    if (!items.length) return;
    const data = await run(() => api<BatchResponse>("POST", `${urls.api}/reconciliations`, { items }));
    if (!data) return;
    const done = data.results.filter((r) => r.status === "ok").map((r) => r.bank_transaction_id);
    removeDone(done, data.counters);
    reportErrors(data.results);
    offerUndo(`${plural(done.length, "transaction rapprochée", "transactions rapprochées")}.`, data.undo);
  }

  function reconcileActive(index = 0) {
    if (!active) return;
    if (active.is_reversed) {
      toast("info", REVERSED_MESSAGE);
      return;
    }
    const list = suggestions.get(active.id);
    const choice = index === 0 ? bestSuggestion(list) : list?.[index - 1];
    if (!choice) {
      toast("info", index === 0 && list && list.length > 1
        ? "Plusieurs suggestions équivalentes : choisissez avec 1…9."
        : "Aucune suggestion pour cette transaction (N pour créer l'écriture).");
      return;
    }
    void reconcile([{ bank_transaction_id: active.id, journal_line_id: choice.journal_line_id }]);
  }

  async function reconcileSelectionBest() {
    const targets = [...selected].filter((id) => !transactions.find((t) => t.id === id)?.is_reversed);
    const lists = await Promise.all(
      targets.map((id) => suggestions.get(id) ?? loadSuggestions(id)));
    const items = targets.flatMap((id, i) => {
      const best = bestSuggestion(lists[i]);
      return best ? [{ bank_transaction_id: id, journal_line_id: best.journal_line_id }] : [];
    });
    const skipped = targets.length - items.length;
    if (skipped) toast("info", `${plural(skipped, "transaction ignorée", "transactions ignorées")} : pas de suggestion unique.`);
    await reconcile(items);
  }

  async function autoReconcile() {
    if (!bankAccountId) return;
    const body: Record<string, unknown> = { bank_account_id: bankAccountId };
    if (selected.size) body.bank_transaction_ids = [...selected];
    const data = await run(() => api<BatchResponse>("POST", `${urls.api}/reconciliations/auto`, body));
    if (!data) return;
    const done = data.results.filter((r) => r.status === "ok").map((r) => r.bank_transaction_id);
    removeDone(done, data.counters);
    if (!done.length) toast("info", "Aucun rapprochement automatique possible (date et montant exacts, sans ambiguïté).");
    offerUndo(`${plural(done.length, "transaction rapprochée", "transactions rapprochées")} automatiquement.`, data.undo);
  }

  async function applyRules() {
    const targets = selected.size ? [...selected] : active ? [active.id] : [];
    if (!targets.length) return;
    const data = await run(() => api<ApplyRulesResponse>(
      "POST", `${urls.api}/bank-transactions/apply-rules`, { ids: targets }));
    if (!data) return;
    data.errors.slice(0, 3).forEach((e) => toast("warning", e));
    toast("info", `Règles : ${data.summary.matched} catégorisée(s), ${data.summary.posted} écriture(s) générée(s).`);
    await load();
    offerUndo(`${plural(data.summary.posted, "écriture générée", "écritures générées")} par les règles.`, data.undo);
  }

  async function replayUndo() {
    if (!undo) return;
    const { request } = undo;
    setUndo(null);
    window.clearTimeout(undoTimer.current);
    const data = await run(() => api<unknown>(request.method, request.url, request.body));
    if (data === null) return;
    toast("success", "Action annulée.");
    await load();
  }

  function onEntrySaved(entry: EntryResponse) {
    const bt = panelFor;
    setPanelFor(null);
    if (bt && entry.reconciled) {
      removeDone([bt.id], counters && { ...counters, unreconciled: counters.unreconciled - 1 });
      toast("success", `Écriture ${entry.reference} créée et rapprochée.`);
    } else {
      void load();
    }
  }

  // --- sélection et clavier -------------------------------------------------
  function toggle(id: number) {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setAnchorId(id);
  }

  function move(delta: number, extend: boolean) {
    if (!ids.length) return;
    const index = activeId === null ? -1 : ids.indexOf(activeId);
    const nextId = ids[Math.min(Math.max(index + delta, 0), ids.length - 1)];
    if (extend) {
      const anchor = anchorId ?? activeId ?? nextId;
      setAnchorId(anchor);
      setSelected(new Set(rangeIds(ids, anchor, nextId)));
    }
    setActiveId(nextId);
  }

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (panelFor || isTyping(e.target)) return;
    const key = e.key;
    if ((e.ctrlKey || e.metaKey) && key.toLowerCase() === "z") {
      e.preventDefault();
      void replayUndo();
    } else if ((e.ctrlKey || e.metaKey) && key.toLowerCase() === "a") {
      e.preventDefault();
      setSelected(new Set(ids));
    } else if (key === "ArrowDown" || key === "j") {
      e.preventDefault();
      move(1, e.shiftKey);
    } else if (key === "ArrowUp" || key === "k") {
      e.preventDefault();
      move(-1, e.shiftKey);
    } else if (key === " " && active) {
      e.preventDefault();
      toggle(active.id);
    } else if (key === "Enter") {
      e.preventDefault();
      reconcileActive(0);
    } else if (/^[1-9]$/.test(key)) {
      e.preventDefault();
      reconcileActive(Number(key));
    } else if (key.toLowerCase() === "n" && active) {
      e.preventDefault();
      if (active.is_reversed) toast("info", REVERSED_MESSAGE);
      else setPanelFor(active);
    } else if (key.toLowerCase() === "r") {
      e.preventDefault();
      void applyRules();
    } else if (key === "Escape") {
      setSelected(new Set());
    }
  }

  // --- rendu ------------------------------------------------------------------
  const activeSuggestions = active ? suggestions.get(active.id) : undefined;
  const best = bestSuggestion(activeSuggestions);

  return (
    <div onKeyDown={onKeyDown}>
      <div className="d-flex flex-wrap gap-2 align-items-end mb-3">
        <div>
          <label className="form-label small mb-0" htmlFor="rw-account">Compte bancaire</label>
          <select id="rw-account" className="form-select form-select-sm" value={bankAccountId ?? ""}
                  onChange={(e) => setBankAccountId(Number(e.target.value) || null)}>
            {bankAccounts.map((b) => <option key={b.id} value={b.id}>{b.label}</option>)}
          </select>
        </div>
        <div>
          <label className="form-label small mb-0" htmlFor="rw-month">Mois</label>
          <select id="rw-month" className="form-select form-select-sm" value={month}
                  onChange={(e) => setMonth(e.target.value)}>
            <option value="">Tous les mois</option>
            {props.monthOptions.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
        </div>
        <div className="ms-auto small" role="status" aria-live="polite">
          {counters && (
            <span className={counters.unreconciled ? "text-danger" : "text-success"}>
              {plural(counters.unreconciled, "transaction non rapprochée", "transactions non rapprochées")}
              {" "}sur {counters.total}
            </span>
          )}
        </div>
      </div>

      <div className="d-flex flex-wrap gap-2 align-items-center mb-2" role="toolbar" aria-label="Actions groupées">
        <span className="small text-muted">{selected.size ? `${plural(selected.size, "sélectionnée", "sélectionnées")} :` : "Aucune sélection :"}</span>
        <button type="button" className="btn btn-sm btn-success" disabled={busy || !selected.size}
                onClick={() => void reconcileSelectionBest()}>Rapprocher les suggestions ★</button>
        <button type="button" className="btn btn-sm btn-outline-primary" disabled={busy || (!selected.size && !active)}
                onClick={() => void applyRules()} title="R">Appliquer les règles</button>
        <button type="button" className="btn btn-sm btn-outline-secondary" disabled={busy || !bankAccountId}
                onClick={() => void autoReconcile()}>
          Rapprochement automatique{selected.size ? " (sélection)" : ""}
        </button>
        {undo && (
          <span className="alert alert-secondary py-1 px-2 mb-0 small d-inline-flex align-items-center gap-2" role="alert">
            {undo.message}
            <button type="button" className="btn btn-sm btn-link p-0" onClick={() => void replayUndo()}>
              Annuler (Ctrl+Z)
            </button>
          </span>
        )}
      </div>

      <div className="row g-3">
        <div className="col-lg-7">
          {/* Annonce de la transaction active pour les lecteurs d'écran. */}
          <div className="visually-hidden" aria-live="polite" aria-atomic="true">
            {active && `Transaction ${frDate(active.date)}, ${active.label}, ${formatEuros(active.amount_cents)}`
              + (activeSuggestions ? `, ${plural(activeSuggestions.length, "suggestion", "suggestions")}` : "")
              + (selected.has(active.id) ? ", sélectionnée" : "")}
          </div>
          <div ref={tableRef} tabIndex={0} className="border rounded overflow-auto" style={{ maxHeight: "65vh" }}
               role="region" aria-label="Transactions à rapprocher (↑↓ pour naviguer, Entrée pour rapprocher)">
            <table className="table table-sm table-hover mb-0 align-middle">
              <thead className="table-light sticky-top">
                <tr>
                  <th style={{ width: "2rem" }}>
                    <input type="checkbox" className="form-check-input" aria-label="Tout sélectionner"
                           checked={!!ids.length && selected.size === ids.length}
                           onChange={(e) => setSelected(e.target.checked ? new Set(ids) : new Set())} />
                  </th>
                  <th>Date</th><th>Libellé</th><th className="text-end">Montant</th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((t) => {
                  const isActive = t.id === activeId;
                  const hasBest = !!bestSuggestion(suggestions.get(t.id));
                  const attachment = attachmentBadge(t.attachment_status);
                  return (
                    <tr key={t.id} data-bt={t.id} aria-current={isActive || undefined}
                        className={isActive ? "table-primary" : selected.has(t.id) ? "table-info" : ""}
                        onClick={(e) => {
                          if (e.shiftKey && anchorId !== null) setSelected(new Set(rangeIds(ids, anchorId, t.id)));
                          setActiveId(t.id);
                          tableRef.current?.focus();
                        }}>
                      <td onClick={(e) => e.stopPropagation()}>
                        <input type="checkbox" className="form-check-input" tabIndex={-1}
                               aria-label={`Sélectionner ${t.label}`} checked={selected.has(t.id)}
                               onChange={() => toggle(t.id)} />
                      </td>
                      <td className="text-nowrap">{frDate(t.date)}</td>
                      <td>
                        {t.label}
                        {hasBest && <span className="ms-1 text-warning" title="Suggestion unique">★</span>}
                        {t.is_reversed && <span className="badge bg-danger ms-1" title={REVERSED_MESSAGE}>Annulée</span>}
                        {attachment && <span className={`badge ms-1 ${attachment.className}`}>{attachment.label}</span>}
                      </td>
                      <td className={`text-end font-monospace text-nowrap ${t.amount_cents < 0 ? "text-danger" : "text-success"}`}>
                        {formatEuros(t.amount_cents)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {!loading && !transactions.length && (
              <div className="alert alert-success m-2">Toutes les transactions de la période sont rapprochées.</div>
            )}
            {loading && <div className="text-muted small p-2">Chargement…</div>}
          </div>
        </div>

        <div className="col-lg-5">
          <div className="card">
            <div className="card-header small">
              {active
                ? <>Suggestions — <strong>{frDate(active.date)}</strong> {active.label} <span className="font-monospace">{formatEuros(active.amount_cents)}</span></>
                : "Suggestions"}
            </div>
            <div className="card-body p-2">
              {active?.is_reversed && <div className="alert alert-danger small mb-2">{REVERSED_MESSAGE}</div>}
              {active && !active.is_reversed && activeSuggestions === undefined && <div className="text-muted small">Recherche…</div>}
              {active && !active.is_reversed && activeSuggestions?.length === 0 && (
                <div className="text-muted small">Aucune écriture correspondante (même compte, même montant, ±3 jours).</div>
              )}
              {active && !!activeSuggestions?.length && (
                <ol className="list-unstyled mb-0">
                  {activeSuggestions.slice(0, 9).map((s, i) => (
                    <li key={s.journal_line_id} className="d-flex align-items-center gap-2 py-1 border-bottom small">
                      <kbd className="bg-light text-dark border">{i + 1}</kbd>
                      <span className="flex-grow-1">
                        {s === best && <span className="text-warning me-1" title="Meilleure suggestion">★</span>}
                        <strong>{s.reference}</strong> — {frDate(s.entry_date)} — {s.label}
                      </span>
                      <span className="font-monospace">{formatEuros(s.amount_cents)}</span>
                      <button type="button" className="btn btn-sm btn-success py-0" disabled={busy}
                              onClick={() => void reconcile([{ bank_transaction_id: active.id, journal_line_id: s.journal_line_id }])}>
                        Rapprocher
                      </button>
                    </li>
                  ))}
                </ol>
              )}
              {active && !active.is_reversed && (
                <button type="button" className="btn btn-sm btn-outline-primary mt-2" onClick={() => setPanelFor(active)}>
                  Créer l'écriture (N)
                </button>
              )}
            </div>
          </div>
          <details className="small text-muted mt-2">
            <summary>Raccourcis clavier</summary>
            <ul className="mb-0 mt-1">
              <li><kbd>↑</kbd>/<kbd>↓</kbd> (ou <kbd>k</kbd>/<kbd>j</kbd>) : transaction précédente / suivante</li>
              <li><kbd>Entrée</kbd> : rapprocher avec la suggestion ★ ; <kbd>1</kbd>…<kbd>9</kbd> : avec la suggestion n°</li>
              <li><kbd>Espace</kbd> : sélectionner ; <kbd>Maj</kbd>+<kbd>↑↓</kbd> : étendre ; <kbd>Ctrl</kbd>+<kbd>A</kbd> : tout ; <kbd>Échap</kbd> : désélectionner</li>
              <li><kbd>N</kbd> : créer l'écriture de la transaction ; <kbd>R</kbd> : appliquer les règles</li>
              <li><kbd>Ctrl</kbd>+<kbd>Z</kbd> : annuler la dernière action</li>
            </ul>
          </details>
        </div>
      </div>

      {panelFor && bankAccount && (
        <EntryPanel bt={panelFor} bankAccount={bankAccount} props={props}
                    onClose={() => { setPanelFor(null); tableRef.current?.focus(); }}
                    onSaved={onEntrySaved} />
      )}
    </div>
  );
}

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Garde le focus clavier dans le panneau modal (Tab / Maj+Tab bouclent). */
function trapFocus(e: KeyboardEvent<HTMLElement>, container: HTMLElement | null) {
  if (!container) return;
  const items = Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE))
    .filter((el) => el.tabIndex !== -1);
  if (!items.length) return;
  const first = items[0];
  const last = items[items.length - 1];
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault();
    first.focus();
  }
}

function EntryPanel({ bt, bankAccount, props, onClose, onSaved }: {
  bt: BankTransaction;
  bankAccount: BankAccountOption;
  props: WorkspaceProps;
  onClose: () => void;
  onSaved: (entry: EntryResponse) => void;
}) {
  const { fiscalYears, journals, defaultJournalId, recentsScope } = props.entryForm;
  const fy = fiscalYears.find((f) => f.start_date <= bt.date && bt.date <= f.end_date) ?? null;
  const amount = Math.abs(bt.amount_cents);
  const inflow = bt.amount_cents >= 0;
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Focus sur la contrepartie (2e ligne) : la ligne banque est préremplie.
    window.setTimeout(() => {
      panelRef.current?.querySelector<HTMLInputElement>('[aria-label="Compte, ligne 2"]')?.focus();
    }, 0);
  }, []);

  return (
    <div className="offcanvas offcanvas-end show" style={{ width: "min(56rem, 100vw)", visibility: "visible" }}
         role="dialog" aria-modal="true" aria-label="Créer l'écriture" ref={panelRef}
         onKeyDown={(e) => {
           if (e.key === "Escape") {
             e.stopPropagation();
             onClose();
           } else if (e.key === "Tab") {
             trapFocus(e, panelRef.current);
           }
         }}>
      <div className="offcanvas-header border-bottom">
        <h5 className="offcanvas-title">Créer l'écriture</h5>
        <button type="button" className="btn-close" aria-label="Fermer (Échap)" onClick={onClose} />
      </div>
      <div className="offcanvas-body">
        <EntryForm
          mode="create"
          fiscalYears={fiscalYears}
          journals={journals}
          initial={{
            fiscal_year_id: fy?.id ?? null,
            journal_id: defaultJournalId,
            entry_date: bt.date,
            description: bt.label,
            lines: [{
              account: bankAccount.account,
              label: bt.label,
              debit_cents: inflow ? amount : 0,
              credit_cents: inflow ? 0 : amount,
            }],
          }}
          bankTransaction={{ id: bt.id, date: bt.date, label: bt.label, amount_cents: bt.amount_cents }}
          urls={{ api: props.urls.api, cancel: "#" }}
          recentsScope={recentsScope}
          onSaved={onSaved}
          onCancel={onClose}
        />
      </div>
    </div>
  );
}
