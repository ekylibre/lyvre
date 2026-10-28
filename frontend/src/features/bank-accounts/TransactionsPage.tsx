// Banque › Transactions d'un compte : filtres (à rapprocher, justificatif manquant, débit sans
// facture, mois), synchronisation et paramètres Qonto, alertes (annulées encore rapprochées,
// contreparties à valider), attribution d'un vrai tiers aux transactions passées par une règle.
import { useState } from "react";
import { useParams } from "react-router";
import { Alert, Anchor, Button, Center, Group, List, Loader, Paper, SegmentedControl, Stack, Text } from "@mantine/core";
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
import type { BankTransaction } from "../../lib/types";
import { AppLink } from "../../app/navigation";
import { attachmentBadge } from "../reconciliation/logic";
import { BANK_ACCOUNTS_KEY, type BankAccount } from "./types";

type Transaction = BankTransaction & {
  raw_type: string | null; note: string | null; entity_id: number | null;
  invoices: { id: number; label: string; url: string }[];
  /** Passée par une règle (pièce + règlement par un compte de tiers) : un vrai tiers peut être attribué. */
  rule_tiers: boolean;
};
interface Detail {
  item: BankAccount; qonto_job: Job | null; proposal_count: number;
  reversed_reconciled: { id: number; date: string; label: string; amount_cents: number; entry: { reference: string; url: string } | null }[];
  meta: { months: MonthOption[]; qonto: { available: boolean; message: string | null } };
}

const FILTERS = [
  { value: "all", label: "Toutes" }, { value: "unreconciled", label: "À rapprocher" },
  { value: "missing", label: "Justificatif manquant" }, { value: "no_invoice", label: "Débit sans facture" },
];

function QontoResult({ r, baId }: { r: Record<string, number | string[] | undefined>; baId: number }) {
  const n = (k: string) => Number(r[k] ?? 0);
  return (
    <Stack gap={2}>
      <Text size="sm">{n("created")} nouvelle(s), {n("updated")} mise(s) à jour, {n("reversed")} annulée(s) sur {n("read")} lue(s).
        {n("rules_matched") > 0 && ` Règles : ${n("rules_matched")} catégorisée(s), ${n("rules_posted")} écriture(s).`}
        {n("settled") > 0 && ` ${n("settled")} règlement(s) de facture d'achat passé(s).`}
        {n("linked_entities") > 0 && ` ${n("linked_entities")} rattachée(s) à un tiers existant.`}</Text>
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
  const [params, setParams] = useUrlParams({ filter: "all", month: "", sort: "desc" });
  const [assigning, setAssigning] = useState<Transaction | null>(null);
  const { data: detail } = useQuery({ queryKey: [...BANK_ACCOUNTS_KEY, baId],
    queryFn: () => api.get<Detail>(`/api/v1/bank-accounts/${baId}`) });
  const query = new URLSearchParams({
    status: params.filter === "unreconciled" ? "unreconciled" : "all", sort: params.sort,
    ...(params.month ? { month: params.month } : {}),
    ...(params.filter === "missing" ? { missing: "1" } : {}), ...(params.filter === "no_invoice" ? { no_invoice: "1" } : {}),
  }).toString();
  const { data, isFetching } = useQuery({
    queryKey: [...BANK_ACCOUNTS_KEY, baId, "transactions", query], placeholderData: (prev) => prev,
    queryFn: () => api.get<{ transactions: Transaction[] }>(`/api/v1/bank-accounts/${baId}/transactions?${query}`),
  });
  if (!detail) return <Center h={300}><Loader /></Center>;
  const ba = detail.item;

  const columns: GridColumn<Transaction>[] = [
    { accessor: "date", title: "Date", sortable: true, hideable: false, render: (t) => <span className="lv-num">{formatDate(t.date)}</span> },
    { accessor: "label", title: "Libellé", hideable: false, render: (t) => {
      const attachment = attachmentBadge(t.attachment_status);
      return (
        <Stack gap={2}>
          <Group gap={6}><Text size="sm">{t.label || "—"}</Text>
            {t.is_reversed && <StatusBadge tone="gap">Annulée</StatusBadge>}
            {attachment && <StatusBadge tone={attachment.tone}>{attachment.label}</StatusBadge>}
            {t.invoices.map((inv) => <Anchor key={inv.id} href={inv.url} size="xs"><StatusBadge tone="info">{inv.label}</StatusBadge></Anchor>)}
            {t.purchase_from_attachment && can.write && (
              <Button size="compact-xs" variant="light" component={AppLink} href={`/purchases/new?bank_transaction_id=${t.id}`}
                title="Lit le justificatif Qonto et prépare la facture d'achat, réglée par cette transaction">
                Créer la facture</Button>)}</Group>
          {t.note && <Text size="xs" c="dimmed">{t.note}</Text>}
        </Stack>
      );
    } },
    { accessor: "raw_type", title: "Type", render: (t) => <Text size="sm" c="dimmed">{t.raw_type ?? "—"}</Text> },
    { accessor: "amount_cents", title: "Montant", textAlign: "right", render: (t) => <MoneyText cents={t.amount_cents} plus /> },
    { accessor: "entity", title: "Tiers", render: (t) => (
      <Group gap={6} wrap="nowrap">
        {t.entity && t.entity_id
          ? <Anchor component={AppLink} href={`/entities/${t.entity_id}`} size="sm">{t.entity}</Anchor>
          : <Text size="sm" c="dimmed">{t.rule_tiers ? "Tiers par défaut" : "—"}</Text>}
        {t.rule_tiers && <Can><Button size="compact-xs" variant="subtle" onClick={() => setAssigning(t)}>
          {t.entity ? "Changer" : "Attribuer"}</Button></Can>}
      </Group>
    ) },
    { accessor: "category", title: "Catégorie", render: (t) => t.category ?? <Text c="dimmed">—</Text> },
    { accessor: "reconciled", title: "Statut", render: (t) => t.reconciled ? <StatusBadge tone="ok">Rapprochée</StatusBadge> : <StatusBadge tone="todo">À rapprocher</StatusBadge> },
    { accessor: "entry", title: "Écriture", render: (t) => t.entry
      ? <Anchor component={AppLink} href={t.entry.url} className="lv-num" size="sm">{t.entry.reference}</Anchor> : <Text c="dimmed">—</Text> },
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
        <SegmentedControl value={params.filter} onChange={(filter) => setParams({ filter })}
          data={ba.qonto ? FILTERS : FILTERS.filter((f) => f.value !== "missing")} />
        <MonthSelect value={params.month} onChange={(month) => setParams({ month })} options={detail.meta.months} />
      </FilterBar>
      <DataGrid id="bank-transactions" records={data?.transactions} columns={columns} fetching={isFetching} perPage={100}
        sort={{ column: "date", direction: params.sort === "asc" ? "asc" : "desc" }} onSortChange={(s) => setParams({ sort: s.direction })}
        emptyText="Aucune transaction pour ces critères." />
      <AssignEntityModal txn={assigning} onClose={() => setAssigning(null)} />
    </>
  );
}
