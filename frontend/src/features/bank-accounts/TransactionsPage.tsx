// Banque › Transactions d'un compte : filtres (à rapprocher, justificatif manquant, débit sans
// facture, mois), synchronisation et paramètres Qonto, alertes (annulées encore rapprochées,
// contreparties à valider), attribution d'un vrai tiers aux transactions passées par une règle.
import { useState } from "react";
import { useParams } from "react-router";
import { Alert, Anchor, Button, Center, Group, List, Loader, Paper, SegmentedControl, Stack, Text, Tooltip } from "@mantine/core";
import { Ban, FileText } from "lucide-react";
import { DateInput } from "@mantine/dates";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan, useIntegration } from "../../api/session";
import { confirmAction } from "../../components/ConfirmButton";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { IntegrationNotice } from "../../components/IntegrationNotice";
import { JobStatus, type Job } from "../../components/JobStatus";
import { MoneyText } from "../../components/Money";
import { MonthSelect, type MonthOption } from "../../components/MonthSelect";
import { PageHeader } from "../../components/PageHeader";
import { Can } from "../../components/Can";
import { EntitySelect } from "../../components/EntitySelect";
import { FormModal } from "../../components/FormModal";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import type { BankTransaction, Light } from "../../lib/types";
import { LightLegend } from "../../components/bank/LightLegend";
import { RowActions, type RowAction } from "../../components/bank/RowActions";
import { AttachmentIcon, TransactionLight, TransactionTypeIcon } from "../../components/bank/TransactionIcons";
import { AppLink } from "../../app/navigation";
import { SALES_KEY } from "../sales/types";
import { LinkInvoiceModal } from "./LinkInvoiceModal";
import { StatementsCard } from "./StatementsCard";
import { BANK_ACCOUNTS_KEY, type BankAccount } from "./types";

type Transaction = BankTransaction & {
  raw_type: string | null; note: string | null; entity_id: number | null;
  invoices: { id: number; label: string; url: string }[];
  /** Crédit libre : factures de vente ouvertes de même restant dû, à encaisser par cette transaction. */
  sale_proposals: { id: number; number: string; client: string | null; due_date: string | null }[];
  /** Passée par une règle (pièce + règlement par un compte de tiers) : un vrai tiers peut être attribué. */
  rule_tiers: boolean;
  /** Libre, sans facture : peut régler ou encaisser une facture existante, en tout ou partie. */
  can_link_invoice?: boolean;
};
interface Detail {
  item: BankAccount; qonto_job: Job | null; proposal_count: number;
  reversed_reconciled: { id: number; date: string; label: string; amount_cents: number; entry: { reference: string; url: string } | null }[];
  meta: { months: MonthOption[]; qonto: { available: boolean; message: string | null } };
}

// « À rapprocher » et « Justificatif manquant » sont portés par la légende des feux (orange) depuis le lot TX2.
const FILTERS = [{ value: "all", label: "Toutes" }, { value: "no_invoice", label: "Débit sans facture" }];
const LIGHTS: Light[] = ["green", "orange", "red"];

function QontoResult({ r, baId }: { r: Record<string, number | string[] | undefined>; baId: number }) {
  const n = (k: string) => Number(r[k] ?? 0);
  return (
    <Stack gap={2}>
      <Text size="sm">{n("created")} nouvelle(s), {n("updated")} mise(s) à jour, {n("reversed")} annulée(s) sur {n("read")} lue(s).
        {n("rules_matched") > 0 && ` Règles : ${n("rules_matched")} catégorisée(s), ${n("rules_posted")} écriture(s).`}
        {n("settled") > 0 && ` ${n("settled")} règlement(s) de facture d'achat passé(s).`}
        {n("linked_entities") > 0 && ` ${n("linked_entities")} rattachée(s) à un tiers existant.`}
        {n("statements") > 0 && ` ${n("statements")} relevé(s) de compte récupéré(s).`}</Text>
      {n("proposed_counterparties") > 0 && <Anchor component={AppLink} href={`/bank-accounts/${baId}/counterparties`} size="sm">
        {n("proposed_counterparties")} contrepartie(s) à valider</Anchor>}
      {n("reversed_reconciled") > 0 && <Text size="sm" c="var(--lv-brique)">{n("reversed_reconciled")} transaction(s) annulée(s) par Qonto étai(en)t déjà rapprochée(s) : à revoir.</Text>}
      {(r.errors as string[] | undefined)?.slice(0, 5).map((e) => <Text key={e} size="sm" c="var(--lv-brique)">{e}</Text>)}
    </Stack>
  );
}

/** Compte rattaché à Qonto : synchronisation et paramètres ; rien si l'intégration est désactivée
 * (le badge « Qonto » du compte et les transactions importées restent). */
function QontoCard({ detail, onSynced }: { detail: Detail; onSynced: () => void }) {
  const can = useCan();
  const enabled = useIntegration("qonto", "transactions");
  const ba = detail.item;
  const [job, setJob] = useState<Job | null>(detail.qonto_job);
  const [syncFrom, setSyncFrom] = useState<string | null>(ba.qonto?.sync_from ?? null);
  const start = useAction<void, { job: Job; notices?: Notice[] }>(() => api.post(`/api/v1/bank-accounts/${ba.id}/qonto/sync`));
  const settings = useAction(() => api.patch<{ notices: Notice[] }>(`/api/v1/bank-accounts/${ba.id}/qonto`, { sync_from: syncFrom }),
    { invalidate: [BANK_ACCOUNTS_KEY] });
  const unlink = useAction(() => api.delete<{ notices: Notice[] }>(`/api/v1/bank-accounts/${ba.id}/qonto`), { invalidate: [BANK_ACCOUNTS_KEY] });
  if (!ba.qonto || !enabled) return null;
  return (
    <Paper p="md" mb="md">
      <Group justify="space-between" align="flex-start">
        <Stack gap={2}>
          <Group gap="xs"><StatusBadge tone="info">Qonto</StatusBadge><Text size="sm">Synchronisé à partir du {formatDate(ba.qonto.sync_from)}</Text></Group>
          <Text size="sm" c="dimmed">Dernière synchronisation : {ba.qonto.synced_at ? `${formatDate(ba.qonto.synced_at)} à ${ba.qonto.synced_at.slice(11, 16)}` : "jamais"}</Text>
        </Stack>
        <Can><Button loading={start.isPending} disabled={!detail.meta.qonto.available || job?.status === "running"}
          onClick={() => start.mutate(undefined, { onSuccess: (r) => setJob(r.job) })}>Synchroniser Qonto</Button></Can>
      </Group>
      <IntegrationNotice name="qonto" state={detail.meta.qonto} consequence="synchronisation impossible" />
      {job && <JobStatus key={job.id} job={job} onDone={onSynced} renderResult={(r) => <QontoResult r={r as never} baId={ba.id} />} />}
      {can.instanceAdmin && (
        <Group align="flex-end" mt="sm" gap="sm">
          <DateInput label="Synchroniser à partir du" valueFormat="DD/MM/YYYY" value={syncFrom} onChange={setSyncFrom} w={200}
            description="Reculer la date relance une synchronisation complète, sans doublon." />
          <Button variant="default" loading={settings.isPending} disabled={!syncFrom || syncFrom === ba.qonto.sync_from}
            onClick={() => settings.mutate(undefined)}>Enregistrer la date</Button>
          <Button variant="subtle" color="brique" onClick={() => confirmAction({
            title: "Détacher ce compte de Qonto ?", message: "Les transactions déjà importées sont conservées.",
            confirmLabel: "Détacher", onConfirm: () => unlink.mutate(undefined) })}>Détacher de Qonto</Button>
        </Group>
      )}
    </Paper>
  );
}

/** Attribue un vrai tiers à une transaction passée par une règle : ses deux écritures sont repassées sur
 * le compte du tiers (supprimées en brouillard, contrepassées si validées). */
function AssignEntityModal({ txn, onClose }: { txn: Transaction | null; onClose: () => void }) {
  const [entityId, setEntityId] = useState("");
  const assign = useAction((id: number) => api.post<{ notices: Notice[] }>(`/api/v1/bank-transactions/${id}/entity`,
    { entity_id: Number(entityId) }), { invalidate: [BANK_ACCOUNTS_KEY] });
  const close = () => { setEntityId(""); onClose(); };
  return (
    <FormModal opened={txn !== null} onClose={close} title="Attribuer à un tiers">
      {txn && <Stack>
        <Text size="sm">{formatDate(txn.date)} — {txn.label || "(sans libellé)"} — <MoneyText cents={txn.amount_cents} /></Text>
        <Text size="sm" c="dimmed">La pièce et le règlement passés par la règle sont repassés sur le compte du tiers
          (créé au besoin) ; validées, les écritures d'origine sont contrepassées.</Text>
        <EntitySelect label="Tiers" value={entityId} onChange={(id) => setEntityId(id)} initialLabel={txn.entity} data-autofocus />
        <Group justify="flex-end">
          <Button variant="default" onClick={close}>Annuler</Button>
          <Button disabled={!entityId} loading={assign.isPending}
            onClick={() => assign.mutate(txn.id, { onSuccess: close })}>Attribuer</Button>
        </Group>
      </Stack>}
    </FormModal>
  );
}

export default function TransactionsPage() {
  const baId = Number(useParams().ba_id);
  const client = useQueryClient();
  const can = useCan();
  const [params, setParams] = useUrlParams({ filter: "all", month: "", sort: "desc", light: "" });
  // Anciennes adresses (filtre « À rapprocher » / « Justificatif manquant ») : feu orange.
  const legacy = params.filter === "unreconciled" || params.filter === "missing";
  const light = (legacy ? "orange" : LIGHTS.find((l) => l === params.light) ?? null) as Light | null;
  const filter = legacy ? "all" : params.filter;
  const [assigning, setAssigning] = useState<Transaction | null>(null);
  const [linking, setLinking] = useState<Transaction | null>(null);
  const cash = useAction((v: { txn: Transaction; saleId: number }) => api.post<{ notices: Notice[] }>("/api/v1/sales/match",
    { bank_transaction_id: v.txn.id, allocations: [{ sale_id: v.saleId, amount_cents: v.txn.amount_cents }] }),
  { invalidate: [BANK_ACCOUNTS_KEY, SALES_KEY] });
  const { data: detail } = useQuery({ queryKey: [...BANK_ACCOUNTS_KEY, baId],
    queryFn: () => api.get<Detail>(`/api/v1/bank-accounts/${baId}`) });
  const query = new URLSearchParams({
    status: "all", sort: params.sort, ...(params.month ? { month: params.month } : {}),
    ...(filter === "no_invoice" ? { no_invoice: "1" } : {}), ...(light ? { light } : {}),
  }).toString();
  const { data, isFetching } = useQuery({
    queryKey: [...BANK_ACCOUNTS_KEY, baId, "transactions", query], placeholderData: (prev) => prev,
    queryFn: () => api.get<{ transactions: Transaction[]; lights?: Record<Light, number> }>(
      `/api/v1/bank-accounts/${baId}/transactions?${query}`),
  });
  if (!detail) return <Center h={300}><Loader /></Center>;
  const ba = detail.item;

  /** Actions d'une ligne, par priorité : la première est visible, les autres dans le menu « … ». */
  const actionsOf = (t: Transaction): RowAction[] => {
    if (!can.write) return [];
    const out: RowAction[] = (t.sale_proposals ?? []).map((s) => ({
      key: `sale-${s.id}`, label: `Encaisser ${s.number}`, loading: cash.isPending && cash.variables?.saleId === s.id,
      title: `Encaisse la facture ${s.number}${s.client ? ` (${s.client})` : ""} par cette transaction : écriture de banque, TVA et rapprochement`,
      onClick: () => confirmAction({
        title: `Encaisser la facture ${s.number} ?`,
        message: `${s.client ?? "Client"} — ${formatDate(t.date)} — l'écriture d'encaissement est passée au journal de banque et rapprochée de cette transaction.`,
        confirmLabel: "Encaisser", onConfirm: () => cash.mutate({ txn: t, saleId: s.id }) }),
    }));
    if (t.purchase_from_attachment) {
      out.push({ key: "purchase", label: "Créer la facture", href: `/purchases/new?bank_transaction_id=${t.id}`,
        title: "Lit le justificatif Qonto et prépare la facture d'achat, réglée par cette transaction" });
    }
    if (t.can_link_invoice) {
      out.push({ key: "link", label: "Rattacher à une facture", onClick: () => setLinking(t),
        title: t.amount_cents < 0 ? "Règle (tout ou partie) une facture d'achat existante par cette transaction"
          : "Encaisse (tout ou partie) une facture de vente existante par cette transaction" });
    }
    if (t.rule_tiers) out.push({ key: "tiers", label: t.entity ? "Changer le tiers" : "Attribuer le tiers", onClick: () => setAssigning(t) });
    if (!t.reconciled && !t.is_reversed) {
      if (t.new_entry_url) out.push({ key: "entry", label: "Nouvelle écriture", href: t.new_entry_url });
      out.push({ key: "reconcile", label: "Rapprocher", href: `/reconciliation/?bank_account_id=${ba.id}` });
    }
    return out;
  };

  const columns: GridColumn<Transaction>[] = [
    { accessor: "light", title: "", hideable: false, width: 36,
      render: (t) => <TransactionLight light={t.light} reasons={t.light_reasons} /> },
    { accessor: "date", title: "Date", sortable: true, hideable: false, render: (t) => <span className="lv-num">{formatDate(t.date)}</span> },
    { accessor: "raw_type", title: "Type", width: 56, textAlign: "center",
      render: (t) => <TransactionTypeIcon rawType={t.raw_type} amountCents={t.amount_cents} /> },
    { accessor: "label", title: "Libellé", hideable: false, render: (t) => (
      <Stack gap={4}>
        <Text size="sm">{t.label || "—"}</Text>
        {(t.is_reversed || t.invoices.length > 0 || t.note) && (
          <Group gap={8}>
            {t.is_reversed && <Group gap={4} wrap="nowrap" c="var(--lv-brique-ink)"><Ban size={14} aria-hidden />
              <Text size="xs" fw={600}>Annulée par la banque</Text></Group>}
            {t.invoices.map((inv) => <Anchor key={inv.id} href={inv.url} size="xs" fw={600} c="var(--lv-ardoise)"
              style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><FileText size={14} aria-hidden />{inv.label}</Anchor>)}
            {t.note && <Text size="xs" c="dimmed">{t.note}</Text>}
          </Group>
        )}
      </Stack>
    ) },
    { accessor: "attachment_status", title: "Pièce", width: 64, textAlign: "center",
      render: (t) => <AttachmentIcon status={t.attachment_status} /> },
    { accessor: "entity", title: "Tiers", render: (t) => t.entity && t.entity_id
      ? <Anchor component={AppLink} href={`/entities/${t.entity_id}`} size="sm">{t.entity}</Anchor>
      : <Text size="sm" c="dimmed">{t.rule_tiers ? "Tiers par défaut" : "—"}</Text> },
    { accessor: "category", title: "Catégorie", render: (t) => {
      const cat = t.category_display;
      if (!cat) return <Text c="dimmed">—</Text>;
      return cat.source === "qonto"
        ? <Tooltip label="Catégorie Qonto" withArrow openDelay={150}><Text size="sm" c="var(--lv-ink-muted)">{cat.label}</Text></Tooltip>
        : <Text size="sm">{cat.label}</Text>;
    } },
    { accessor: "amount_cents", title: "Montant", textAlign: "right", render: (t) => <MoneyText cents={t.amount_cents} plus /> },
    { accessor: "entry", title: "Écriture", render: (t) => t.entry
      ? <Anchor component={AppLink} href={t.entry.url} className="lv-num" size="sm">{t.entry.reference}</Anchor> : <Text c="dimmed">—</Text> },
    { accessor: "actions", title: "Actions", hideable: false, textAlign: "right",
      render: (t) => <RowActions actions={actionsOf(t)} label={t.label || formatDate(t.date)} /> },
  ];

  return (
    <>
      <PageHeader title={ba.label} description={`${ba.account.code} — ${ba.account.label}${ba.iban ? ` · ${ba.iban}` : ""}`}
        actions={<>
          <Button variant="default" component={AppLink} href="/bank-accounts/">Retour aux comptes</Button>
          <Button variant="default" component={AppLink} href="/rules/">Règles</Button>
          <Can>{!ba.qonto && <Button variant="default" component={AppLink} href={`/imports/ofx?bank_account_id=${ba.id}`}>Importer un OFX</Button>}</Can>
          <Can><Button component={AppLink} href={`/reconciliation/?bank_account_id=${ba.id}`}>Rapprocher</Button></Can>
        </>} />
      <QontoCard detail={detail} onSynced={() => void client.invalidateQueries({ queryKey: [...BANK_ACCOUNTS_KEY, baId] })} />
      {ba.kind === "bank" && <StatementsCard bankAccountId={ba.id} />}
      {!ba.qonto && can.instanceAdmin && detail.meta.qonto.available && (
        <Text size="sm" mb="sm"><Anchor component={AppLink} href="/bank-accounts/qonto">Rattacher ce compte à Qonto</Anchor></Text>
      )}
      {detail.reversed_reconciled.length > 0 && (
        <Alert color="brique" role="alert" mb="sm" title={`${detail.reversed_reconciled.length} transaction(s) annulée(s) par la banque encore rapprochée(s)`}>
          L'écriture liée est à revoir : défaire le rapprochement, puis corriger ou supprimer l'écriture.
          <List size="sm" mt={4}>{detail.reversed_reconciled.map((t) => (
            <List.Item key={t.id}>{formatDate(t.date)} — {t.label} — <MoneyText cents={t.amount_cents} />
              {t.entry && <> — <Anchor component={AppLink} href={t.entry.url}>{t.entry.reference}</Anchor></>}</List.Item>))}</List>
        </Alert>
      )}
      {detail.proposal_count > 0 && (
        <Alert color="ardoise" variant="light" mb="sm">
          {detail.proposal_count} contrepartie(s) de débits sans tiers à valider (créer le fournisseur, rattacher ou ignorer).{" "}
          <Anchor component={AppLink} href={`/bank-accounts/${ba.id}/counterparties`}>Valider les contreparties</Anchor>
        </Alert>
      )}
      <FilterBar>
        <LightLegend counts={data?.lights} value={light} onChange={(l) => setParams({ light: l ?? "", filter })} />
        <SegmentedControl value={filter} onChange={(f) => setParams({ filter: f })} data={FILTERS} />
        <MonthSelect value={params.month} onChange={(month) => setParams({ month })} options={detail.meta.months} />
      </FilterBar>
      <DataGrid id="bank-transactions" records={data?.transactions} columns={columns} fetching={isFetching} perPage={100}
        sort={{ column: "date", direction: params.sort === "asc" ? "asc" : "desc" }} onSortChange={(s) => setParams({ sort: s.direction })}
        emptyText="Aucune transaction pour ces critères." />
      <AssignEntityModal txn={assigning} onClose={() => setAssigning(null)} />
      <LinkInvoiceModal txn={linking} onClose={() => setLinking(null)} />
    </>
  );
}
