// Banque › Rapprochement : transactions non rapprochées d'un compte et suggestions
// d'écritures (même compte, même montant, ±3 jours). Clavier : ↑↓ / j k, Entrée (★),
// 1…9, Espace, Maj+↑↓, Ctrl+A, N (créer l'écriture), R (règles), Ctrl+Z, Échap.
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useSearchParams } from "react-router";
import {
  Alert, Anchor, Button, Center, Checkbox, Drawer, Grid, Group, Kbd, List, Loader, Menu, Paper, Select,
  Stack, Table, Text, Title, VisuallyHidden,
} from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { notifications } from "@mantine/notifications";
import { Star } from "lucide-react";
import { api, ApiError, request } from "../../api/client";
import { MoneyText } from "../../components/Money";
import { MonthSelect, type MonthOption } from "../../components/MonthSelect";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate, formatEuros } from "../../lib/format";
import type { ApplyRulesResponse, BankTransaction, BatchResponse, Counters, Suggestion, UndoRequest } from "../../lib/types";
import { AppLink } from "../../app/navigation";
import { EntryEditor, type EntryFormData } from "../entries/EntryEditor";
import { activeAfterRemoval, bestSuggestion, plural, rangeIds, REVERSED_MESSAGE } from "./logic";
import { LightLegend } from "../../components/bank/LightLegend";
import { AttachmentIcon, TransactionLight, TransactionTypeIcon } from "../../components/bank/TransactionIcons";
import { writeOnly } from "../../components/ReadOnlyPage";
import { useCurrentSession } from "../../api/session";
import { ASSOCIATES_KEY, type Associate } from "../associates/types";

const UNDO_VISIBLE_MS = 10_000;
const PREFETCH_NEXT = 3;

interface Context {
  bank_accounts: { id: number; label: string; account: { id: number; code: string; label: string } }[];
  months: MonthOption[];
}

const notify = (color: string, message: string) => notifications.show({ color, message });

/** Raccourcis ignorés quand on tape dans un champ. */
function isTyping(target: EventTarget | null) {
  const el = target as HTMLElement | null;
  return !!el && (el.tagName === "INPUT" || el.tagName === "SELECT" || el.tagName === "TEXTAREA" || el.isContentEditable);
}

/** Panneau « Créer l'écriture » : formulaire préparé par le serveur depuis la transaction. */
function EntryPanel({ bt, associateId, onClose, onSaved }: {
  bt: BankTransaction; associateId?: number | null; onClose: () => void; onSaved: (reconciled: boolean, reference: string) => void;
}) {
  // Avec un associé : apport ou remboursement de son compte courant (contrepartie 455 préremplie).
  const { data, error } = useQuery({
    queryKey: ["entries", "form", "bt", bt.id, associateId ?? null], gcTime: 0, retry: false,
    queryFn: () => api.get<EntryFormData>(`/api/v1/entries/form?bt_id=${bt.id}${associateId ? `&associate_id=${associateId}` : ""}`),
  });
  return (
    <Drawer opened onClose={onClose} position="right" size="min(56rem, 100vw)" title="Créer l'écriture">
      {error ? <Alert color="brique" role="alert">{(error as Error).message}</Alert>
        : !data ? <Center h={200}><Loader /></Center>
          : <EntryEditor data={data} focusAccountOfLine={1} onCancel={onClose}
              onSaved={(entry) => onSaved(entry.reconciled, entry.reference)} />}
    </Drawer>
  );
}

function ReconcilePage() {
  const [search, setSearch] = useSearchParams();
  const { data: context } = useQuery({ queryKey: ["reconciliation", "context"],
    queryFn: () => api.get<Context>("/api/v1/reconciliation/context") });
  const bankAccounts = context?.bank_accounts ?? [];
  const requested = Number(search.get("bank_account_id")) || null;
  const bankAccountId = bankAccounts.some((b) => b.id === requested) ? requested : bankAccounts[0]?.id ?? null;
  const month = search.get("month") ?? "";
  const setFilter = (key: string, value: string) => setSearch((current) => {
    const next = new URLSearchParams(current);
    if (value) next.set(key, value); else next.delete(key);
    return next;
  }, { replace: true });

  const [transactions, setTransactions] = useState<BankTransaction[]>([]);
  const [counters, setCounters] = useState<Counters | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [anchorId, setAnchorId] = useState<number | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [suggestions, setSuggestions] = useState<Map<number, Suggestion[]>>(new Map());
  const [busy, setBusy] = useState(false);
  const [undo, setUndo] = useState<{ message: string; request: UndoRequest } | null>(null);
  const [panelFor, setPanelFor] = useState<BankTransaction | null>(null);
  const [panelAssociate, setPanelAssociate] = useState<number | null>(null);
  const session = useCurrentSession();
  const associates = useQuery({ queryKey: [...ASSOCIATES_KEY, "/api/v1/associates"], enabled: !!session.instance?.has_associates,
    queryFn: () => api.get<{ items: Associate[] }>("/api/v1/associates") });
  const tableRef = useRef<HTMLDivElement>(null);
  const undoTimer = useRef<number | undefined>(undefined);
  const pending = useRef(new Set<number>());

  const ids = useMemo(() => transactions.map((t) => t.id), [transactions]);
  const active = transactions.find((t) => t.id === activeId) ?? null;

  const load = useCallback(async () => {
    if (!bankAccountId) { setLoading(false); return; }
    setLoading(true);
    const params = new URLSearchParams({ status: "unreconciled", sort: "asc" });
    if (month) params.set("month", month);
    try {
      const data = await api.get<{ transactions: BankTransaction[]; counters: Counters }>(
        `/api/v1/bank-accounts/${bankAccountId}/transactions?${params}`);
      setTransactions(data.transactions);
      setCounters(data.counters);
      setSelected(new Set());
      setSuggestions(new Map());
      pending.current.clear();
      setActiveId((current) => data.transactions.some((t) => t.id === current) ? current : data.transactions[0]?.id ?? null);
    } catch (err) {
      notify("brique", err instanceof ApiError ? err.message : "Chargement impossible.");
    }
    setLoading(false);
  }, [bankAccountId, month]);

  useEffect(() => { void load(); }, [load]);

  const loadSuggestions = useCallback(async (btId: number): Promise<Suggestion[] | undefined> => {
    try {
      const data = await api.get<{ suggestions: Suggestion[] }>(`/api/v1/bank-transactions/${btId}/suggestions`);
      setSuggestions((m) => new Map(m).set(btId, data.suggestions));
      return data.suggestions;
    } catch {
      return undefined;
    }
  }, []);

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

  useEffect(() => {
    if (activeId === null) return;
    tableRef.current?.querySelector(`[data-bt="${activeId}"]`)?.scrollIntoView({ block: "nearest" });
  }, [activeId]);

  function offerUndo(message: string, request: UndoRequest | null) {
    window.clearTimeout(undoTimer.current);
    if (!request) { setUndo(null); return; }
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
    if (failed.length === 1) notify("paille", failed[0].message ?? "Rapprochement refusé.");
    else if (failed.length > 1) notify("paille", `${plural(failed.length, "transaction non rapprochée", "transactions non rapprochées")} (contrôles de montant / compte).`);
  }

  async function run<T>(action: () => Promise<T>): Promise<T | null> {
    if (busy) return null;
    setBusy(true);
    try {
      return await action();
    } catch (err) {
      notify("brique", err instanceof ApiError ? err.message : "Action impossible.");
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function reconcile(items: { bank_transaction_id: number; journal_line_id: number }[]) {
    if (!items.length) return;
    const data = await run(() => api.post<BatchResponse>("/api/v1/reconciliations", { items }));
    if (!data) return;
    const done = data.results.filter((r) => r.status === "ok").map((r) => r.bank_transaction_id);
    removeDone(done, data.counters);
    reportErrors(data.results);
    offerUndo(`${plural(done.length, "transaction rapprochée", "transactions rapprochées")}.`, data.undo);
  }

  function reconcileActive(index = 0) {
    if (!active) return;
    if (active.is_reversed) { notify("ardoise", REVERSED_MESSAGE); return; }
    const list = suggestions.get(active.id);
    const choice = index === 0 ? bestSuggestion(list) : list?.[index - 1];
    if (!choice) {
      notify("ardoise", index === 0 && list && list.length > 1
        ? "Plusieurs suggestions équivalentes : choisissez avec 1…9."
        : "Aucune suggestion pour cette transaction (N pour créer l'écriture).");
      return;
    }
    void reconcile([{ bank_transaction_id: active.id, journal_line_id: choice.journal_line_id }]);
  }

  async function reconcileSelectionBest() {
    const targets = [...selected].filter((id) => !transactions.find((t) => t.id === id)?.is_reversed);
    const lists = await Promise.all(targets.map((id) => suggestions.get(id) ?? loadSuggestions(id)));
    const items = targets.flatMap((id, i) => {
      const best = bestSuggestion(lists[i]);
      return best ? [{ bank_transaction_id: id, journal_line_id: best.journal_line_id }] : [];
    });
    const skipped = targets.length - items.length;
    if (skipped) notify("ardoise", `${plural(skipped, "transaction ignorée", "transactions ignorées")} : pas de suggestion unique.`);
    await reconcile(items);
  }

  async function autoReconcile() {
    if (!bankAccountId) return;
    const body: Record<string, unknown> = { bank_account_id: bankAccountId };
    if (selected.size) body.bank_transaction_ids = [...selected];
    const data = await run(() => api.post<BatchResponse>("/api/v1/reconciliations/auto", body));
    if (!data) return;
    const done = data.results.filter((r) => r.status === "ok").map((r) => r.bank_transaction_id);
    removeDone(done, data.counters);
    if (!done.length) notify("ardoise", "Aucun rapprochement automatique possible (date et montant exacts, sans ambiguïté).");
    offerUndo(`${plural(done.length, "transaction rapprochée", "transactions rapprochées")} automatiquement.`, data.undo);
  }

  async function applyRules() {
    const targets = selected.size ? [...selected] : active ? [active.id] : [];
    if (!targets.length) return;
    const data = await run(() => api.post<ApplyRulesResponse>("/api/v1/bank-transactions/apply-rules", { ids: targets }));
    if (!data) return;
    data.errors.slice(0, 3).forEach((e) => notify("paille", e));
    notify("ardoise", `Règles : ${data.summary.matched} catégorisée(s), ${data.summary.posted} écriture(s) générée(s).`);
    await load();
    offerUndo(`${plural(data.summary.posted, "écriture générée", "écritures générées")} par les règles.`, data.undo);
  }

  async function replayUndo() {
    if (!undo) return;
    const { request: undoRequest } = undo;
    setUndo(null);
    window.clearTimeout(undoTimer.current);
    const data = await run(() => request<unknown>(undoRequest.method, undoRequest.url, { body: undoRequest.body }));
    if (data === null) return;
    notify("lichen", "Action annulée.");
    await load();
  }

  function onEntrySaved(reconciled: boolean, reference: string) {
    const bt = panelFor;
    setPanelFor(null);
    if (bt && reconciled) {
      removeDone([bt.id], counters && { ...counters, unreconciled: counters.unreconciled - 1 });
      notify("lichen", `Écriture ${reference} créée et rapprochée.`);
    } else {
      void load();
    }
  }

  function toggle(id: number) {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id); else next.add(id);
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
    if ((e.ctrlKey || e.metaKey) && key.toLowerCase() === "z") { e.preventDefault(); void replayUndo(); }
    else if ((e.ctrlKey || e.metaKey) && key.toLowerCase() === "a") { e.preventDefault(); setSelected(new Set(ids)); }
    else if (key === "ArrowDown" || key === "j") { e.preventDefault(); move(1, e.shiftKey); }
    else if (key === "ArrowUp" || key === "k") { e.preventDefault(); move(-1, e.shiftKey); }
    else if (key === " " && active) { e.preventDefault(); toggle(active.id); }
    else if (key === "Enter") { e.preventDefault(); reconcileActive(0); }
    else if (/^[1-9]$/.test(key)) { e.preventDefault(); reconcileActive(Number(key)); }
    else if (key.toLowerCase() === "n" && active) {
      e.preventDefault();
      if (active.is_reversed) notify("ardoise", REVERSED_MESSAGE); else { setPanelAssociate(null); setPanelFor(active); }
    } else if (key.toLowerCase() === "r") { e.preventDefault(); void applyRules(); }
    else if (key === "Escape") setSelected(new Set());
  }

  const activeSuggestions = active ? suggestions.get(active.id) : undefined;
  const best = bestSuggestion(activeSuggestions);

  if (context && !bankAccounts.length) {
    return (
      <>
        <PageHeader title="Rapprochement" />
        <Alert color="paille">Aucun compte bancaire : <Anchor component={AppLink} href="/bank-accounts/new">créer un compte</Anchor>.</Alert>
      </>
    );
  }

  return (
    <div onKeyDown={onKeyDown}>
      <PageHeader title="Rapprochement" description="Associer chaque transaction bancaire à son écriture."
        actions={counters && (
          <Text role="status" aria-live="polite" fw={600} c={counters.unreconciled ? "var(--lv-paille-ink)" : "var(--lv-lichen)"}>
            {plural(counters.unreconciled, "transaction à rapprocher", "transactions à rapprocher")} sur {counters.total}
          </Text>
        )} />
      <Group gap="sm" mb="sm" align="flex-end">
        <Select label="Compte bancaire" w={260} allowDeselect={false} value={bankAccountId ? String(bankAccountId) : null}
          data={bankAccounts.map((b) => ({ value: String(b.id), label: b.label }))}
          onChange={(v) => setFilter("bank_account_id", v ?? "")} />
        <MonthSelect value={month} onChange={(v) => setFilter("month", v)} options={context?.months} />
      </Group>
      <Group gap="xs" mb="sm" role="toolbar" aria-label="Actions groupées">
        <Text size="sm" c="dimmed">{selected.size ? `${plural(selected.size, "sélectionnée", "sélectionnées")} :` : "Aucune sélection :"}</Text>
        <Button size="compact-md" disabled={busy || !selected.size} onClick={() => void reconcileSelectionBest()}>Rapprocher les suggestions ★</Button>
        <Button size="compact-md" variant="default" disabled={busy || (!selected.size && !active)} title="R"
          onClick={() => void applyRules()}>Appliquer les règles</Button>
        <Button size="compact-md" variant="default" disabled={busy || !bankAccountId} onClick={() => void autoReconcile()}>
          Rapprocher automatiquement{selected.size ? " (sélection)" : ""}</Button>
        {undo && (
          <Paper px="sm" py={4} bg="var(--lv-surface-sunken)" role="alert">
            <Group gap="xs"><Text size="sm">{undo.message}</Text>
              <Button size="compact-sm" variant="subtle" onClick={() => void replayUndo()}>Annuler (Ctrl+Z)</Button></Group>
          </Paper>
        )}
      </Group>

      <Grid gap="md">
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <VisuallyHidden aria-live="polite" aria-atomic="true">
            {active && `Transaction ${formatDate(active.date)}, ${active.label}, ${formatEuros(active.amount_cents)}`
              + (activeSuggestions ? `, ${plural(activeSuggestions.length, "suggestion", "suggestions")}` : "")
              + (selected.has(active.id) ? ", sélectionnée" : "")}
          </VisuallyHidden>
          <Group justify="flex-end" mb={6}><LightLegend /></Group>
          <Paper p={0} ref={tableRef} tabIndex={0} style={{ overflow: "auto", maxHeight: "65vh" }} role="region"
            aria-label="Transactions à rapprocher (↑↓ pour naviguer, Entrée pour rapprocher)">
            <Table highlightOnHover stickyHeader verticalSpacing={6}>
              <Table.Thead bg="var(--lv-sauge)">
                <Table.Tr>
                  <Table.Th w={40}><Checkbox aria-label="Tout sélectionner" checked={!!ids.length && selected.size === ids.length}
                    onChange={(e) => setSelected(e.currentTarget.checked ? new Set(ids) : new Set())} /></Table.Th>
                  <Table.Th w={28}><VisuallyHidden>Feu</VisuallyHidden></Table.Th>
                  <Table.Th>Date</Table.Th><Table.Th w={44}>Type</Table.Th><Table.Th>Libellé</Table.Th>
                  <Table.Th w={52} ta="center">Pièce</Table.Th><Table.Th ta="right">Montant</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {transactions.map((t) => {
                  const isActive = t.id === activeId;
                  return (
                    <Table.Tr key={t.id} data-bt={t.id} aria-current={isActive || undefined} style={{ cursor: "pointer" }}
                      bg={isActive ? "var(--lv-sauge)" : selected.has(t.id) ? "var(--lv-ardoise-tint)" : undefined}
                      onClick={(e) => {
                        if (e.shiftKey && anchorId !== null) setSelected(new Set(rangeIds(ids, anchorId, t.id)));
                        setActiveId(t.id);
                        tableRef.current?.focus();
                      }}>
                      <Table.Td onClick={(e) => e.stopPropagation()}>
                        <Checkbox tabIndex={-1} aria-label={`Sélectionner ${t.label}`} checked={selected.has(t.id)} onChange={() => toggle(t.id)} />
                      </Table.Td>
                      <Table.Td><TransactionLight light={t.light} reasons={t.light_reasons} /></Table.Td>
                      <Table.Td className="lv-num" style={{ whiteSpace: "nowrap" }}>{formatDate(t.date)}</Table.Td>
                      <Table.Td><TransactionTypeIcon rawType={t.raw_type} amountCents={t.amount_cents} /></Table.Td>
                      <Table.Td>
                        <Group gap={6} wrap="wrap">
                          <Text size="sm">{t.label}</Text>
                          {bestSuggestion(suggestions.get(t.id)) && <Star size={14} fill="var(--lv-paille)" color="var(--lv-paille)" aria-label="Suggestion unique" />}
                          {t.is_reversed && <StatusBadge tone="gap">Annulée</StatusBadge>}
                        </Group>
                      </Table.Td>
                      <Table.Td ta="center"><AttachmentIcon status={t.attachment_status} /></Table.Td>
                      <Table.Td ta="right"><MoneyText cents={t.amount_cents} plus /></Table.Td>
                    </Table.Tr>
                  );
                })}
              </Table.Tbody>
            </Table>
            {!loading && !transactions.length && <Alert color="lichen" m="sm">Toutes les transactions de la période sont rapprochées.</Alert>}
            {loading && <Center p="md"><Loader size="sm" /></Center>}
          </Paper>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Paper p="md">
            <Title order={2} size="h3" mb="xs">Suggestions</Title>
            {active && <Text size="sm" mb="sm"><span className="lv-num">{formatDate(active.date)}</span> · {active.label} ·{" "}
              <MoneyText cents={active.amount_cents} plus fw={600} /></Text>}
            <Stack gap={6}>
              {active?.is_reversed && <Alert color="brique">{REVERSED_MESSAGE}</Alert>}
              {active && !active.is_reversed && activeSuggestions === undefined && <Text size="sm" c="dimmed">Recherche…</Text>}
              {active && !active.is_reversed && activeSuggestions?.length === 0 && (
                <Text size="sm" c="dimmed">Aucune écriture correspondante (même compte, même montant, ±3 jours).</Text>
              )}
              {active && activeSuggestions?.slice(0, 9).map((s, i) => (
                <Group key={s.journal_line_id} gap="xs" wrap="nowrap" py={4} style={{ borderBottom: "1px solid var(--lv-line)" }}>
                  <Kbd>{i + 1}</Kbd>
                  <Text size="sm" style={{ flex: 1 }}>
                    {s === best && <Star size={14} fill="var(--lv-paille)" color="var(--lv-paille)" aria-label="Meilleure suggestion" />}{" "}
                    <b className="lv-num">{s.reference}</b> · {formatDate(s.entry_date)} · {s.label}
                  </Text>
                  <MoneyText cents={s.amount_cents} size="sm" />
                  <Button size="compact-sm" disabled={busy}
                    onClick={() => void reconcile([{ bank_transaction_id: active.id, journal_line_id: s.journal_line_id }])}>Rapprocher</Button>
                </Group>
              ))}
              {active && !active.is_reversed && (
                <Group gap="xs" mt="xs">
                  <Button variant="default" w="fit-content" onClick={() => { setPanelAssociate(null); setPanelFor(active); }}>Créer l'écriture (N)</Button>
                  {(associates.data?.items.length ?? 0) > 0 && (
                    <Menu position="bottom-start">
                      <Menu.Target><Button variant="default">Compte courant d'associé</Button></Menu.Target>
                      <Menu.Dropdown>
                        <Menu.Label>{active.amount_cents >= 0 ? "Apport de" : "Remboursement à"}</Menu.Label>
                        {associates.data?.items.map((a) => (
                          <Menu.Item key={a.id} onClick={() => { setPanelAssociate(a.id); setPanelFor(active); }}>{a.name}</Menu.Item>
                        ))}
                      </Menu.Dropdown>
                    </Menu>
                  )}
                </Group>
              )}
            </Stack>
          </Paper>
          <details style={{ marginTop: 12 }}>
            <summary><Anchor component="span" size="sm">Raccourcis clavier</Anchor></summary>
            <List size="sm" c="dimmed" mt={4}>
              <List.Item><Kbd>↑</Kbd> <Kbd>↓</Kbd> (ou <Kbd>k</Kbd> <Kbd>j</Kbd>) : transaction précédente / suivante</List.Item>
              <List.Item><Kbd>Entrée</Kbd> : rapprocher avec la suggestion ★ ; <Kbd>1</Kbd>…<Kbd>9</Kbd> : avec la suggestion n°</List.Item>
              <List.Item><Kbd>Espace</Kbd> : sélectionner ; <Kbd>Maj</Kbd>+<Kbd>↑↓</Kbd> : étendre ; <Kbd>Ctrl</Kbd>+<Kbd>A</Kbd> : tout ; <Kbd>Échap</Kbd> : désélectionner</List.Item>
              <List.Item><Kbd>N</Kbd> : créer l'écriture de la transaction ; <Kbd>R</Kbd> : appliquer les règles</List.Item>
              <List.Item><Kbd>Ctrl</Kbd>+<Kbd>Z</Kbd> : annuler la dernière action</List.Item>
            </List>
          </details>
          {bankAccountId && <Anchor component={AppLink} href={`/bank-accounts/${bankAccountId}/transactions`} size="sm" mt="sm" display="block">
            Toutes les transactions du compte</Anchor>}
        </Grid.Col>
      </Grid>
      {panelFor && <EntryPanel bt={panelFor} associateId={panelAssociate} onClose={() => { setPanelFor(null); tableRef.current?.focus(); }} onSaved={onEntrySaved} />}
    </div>
  );
}

export default writeOnly(ReconcilePage, "Rapprochement bancaire", { href: "/bank-accounts/", label: "Voir les comptes bancaires et leurs transactions." });
