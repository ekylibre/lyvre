// Achats › Factures d'achat : factures reçues dans Qonto ou saisies ; filtres, synchronisation
// Qonto en arrière-plan, comptabilisation des factures prêtes, suppression.
import { useState } from "react";
import { ActionIcon, Alert, Anchor, Badge, Button, Checkbox, Group, Paper, Select, Text, TextInput, Tooltip } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { confirmAction } from "../../components/ConfirmButton";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FilterBar, SearchInput, useUrlParams } from "../../components/FilterBar";
import { IntegrationNotice } from "../../components/IntegrationNotice";
import { JobStatus, type Job } from "../../components/JobStatus";
import { MoneyText } from "../../components/Money";
import { MonthSelect } from "../../components/MonthSelect";
import { PageHeader } from "../../components/PageHeader";
import { Can } from "../../components/Can";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { PURCHASES_KEY, STATE_TONES, type Purchase, type PurchasesMeta } from "./types";

const FILTERS = { q: "", state: "", status: "", source: "", entity_id: "", month: "", unpaid: "", no_supplier: "", hidden: "", sort: "desc" };

export function syncResult(r: Record<string, unknown>) {
  const n = (key: string) => Number(r[key] ?? 0);
  const errors = (r.errors as string[] | undefined) ?? [];
  return (
    <>
      <Text size="sm">
        {n("created")} nouvelle(s), {n("updated")} mise(s) à jour sur {n("read")} lue(s).
        {n("posted") > 0 && ` ${n("posted")} comptabilisée(s).`}
        {n("settled") > 0 && ` ${n("settled")} règlement(s) passé(s).`}
        {n("hidden") > 0 && ` ${n("hidden")} masquée(s) (rejetée, écartée ou non financière).`}
        {n("without_supplier") > 0 && <> <Anchor component={AppLink} href="/purchases/?no_supplier=1" size="sm">{n("without_supplier")} sans fournisseur rattaché</Anchor>.</>}
      </Text>
      {n("to_review") > 0 && <Text size="sm" c="var(--lv-brique)">{n("to_review")} facture(s) comptabilisée(s) modifiée(s) dans Qonto : à revoir.</Text>}
      {errors.slice(0, 5).map((e) => <Text key={e} size="sm" c="var(--lv-brique)">{e}</Text>)}
    </>
  );
}

function deleteMessage(p: Purchase) {
  return [p.journal_entry_id && "Son écriture d'achat sera supprimée aussi.", p.in_qonto && "Elle reste dans Qonto."]
    .filter(Boolean).join(" ") || undefined;
}

function SyncFrom({ value }: { value: string }) {
  const [date, setDate] = useState(value);
  const save = useAction((sync_from: string) => api.patch<{ notices: Notice[] }>("/api/v1/purchases/sync-from", { sync_from }),
    { invalidate: [PURCHASES_KEY] });
  return (
    <Group gap="xs">
      <TextInput type="date" aria-label="Date de début" size="xs" value={date} onChange={(e) => setDate(e.currentTarget.value)} />
      <Tooltip label="Reculer la date relit toutes les factures depuis cette date (sans doublon)">
        <Button size="compact-sm" variant="default" loading={save.isPending} onClick={() => save.mutate(date)}>Enregistrer</Button>
      </Tooltip>
    </Group>
  );
}

export default function PurchasesPage() {
  const client = useQueryClient();
  const can = useCan();
  const [params, setParams] = useUrlParams(FILTERS);
  const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
  const { data, isFetching } = useList<Purchase, PurchasesMeta>(PURCHASES_KEY, `/api/v1/purchases${query ? `?${query}` : ""}`);
  const meta = data?.meta;
  const counters = meta?.counters;
  const [job, setJob] = useState<Job | null>(null);
  const shown = job ?? meta?.sync.job ?? null;
  const sync = useAction<void, { job: Job; notices?: Notice[] }>(() => api.post("/api/v1/purchases/sync"));
  const postReady = useAction(() => api.post<{ notices: Notice[] }>("/api/v1/purchases/post-ready"), { invalidate: [PURCHASES_KEY] });
  const remove = useAction((id: number) => api.delete<{ notices: Notice[] }>(`/api/v1/purchases/${id}`), { invalidate: [PURCHASES_KEY] });
  const filtered = Object.entries(params).some(([k, v]) => k !== "sort" && v);

  const columns: GridColumn<Purchase>[] = [
    { accessor: "issue_date", title: "Date", sortable: true, hideable: false, render: (p) => <span className="lv-num">{formatDate(p.issue_date)}</span> },
    { accessor: "invoice_number", title: "Numéro", hideable: false, render: (p) => (
      <Group gap={6} wrap="nowrap">
        <Anchor component={AppLink} href={`/purchases/${p.id}`} size="sm" className="lv-num">{p.invoice_number || "sans numéro"}</Anchor>
        {p.is_credit_note && <Badge size="xs" variant="light" color="gray">Avoir</Badge>}
        {p.source === "manual" && <Badge size="xs" variant="outline" color="gray" title={p.has_attachment ? "Saisie dans l'application — pièce jointe" : "Saisie dans l'application"}>saisie</Badge>}
        {p.qonto_upload_status === "failed" && <Badge size="xs" color="brique" title={p.qonto_upload_error ?? undefined}>envoi Qonto en échec</Badge>}
        {p.is_einvoice && <Badge size="xs" variant="outline" color="gray" title="Facture électronique">e-facture</Badge>}
      </Group>
    ) },
    { accessor: "supplier", title: "Fournisseur", render: (p) => p.supplier
      ? <Anchor component={AppLink} href={`/entities/${p.supplier.id}`} size="sm">{p.supplier.name}</Anchor>
      : <Group gap={6}><Text size="sm">{p.supplier_name || "—"}</Text><StatusBadge tone="todo">à rattacher</StatusBadge></Group> },
    { accessor: "total_cents", title: "TTC", textAlign: "right", render: (p) => <MoneyText cents={p.is_credit_note ? -p.total_cents : p.total_cents} /> },
    { accessor: "state", title: "État", render: (p) => (
      <Tooltip label={p.state.reasons.join(" ")} disabled={!p.state.reasons.length} multiline w={320}>
        <span><StatusBadge tone={STATE_TONES[p.state.code]}>{p.state.label}</StatusBadge></span>
      </Tooltip>
    ) },
    { accessor: "qonto_status", title: "Statut Qonto", render: (p) => (
      <Group gap={6} wrap="nowrap"><Text size="sm">{p.qonto_status_label ?? "—"}</Text>
        {p.review_reason && <Tooltip label={p.review_reason} multiline w={320}><span><StatusBadge tone="gap">à revoir</StatusBadge></span></Tooltip>}</Group>
    ) },
    { accessor: "due_date", title: "Échéance", render: (p) => <span className="lv-num">{formatDate(p.due_date)}</span> },
    { accessor: "actions", title: "", hideable: false, textAlign: "right", render: (p) => (
      <ActionIcon variant="subtle" color="red" aria-label={`Supprimer ${p.is_credit_note ? "l'avoir" : "la facture"} ${p.invoice_number || "sans numéro"}`}
        onClick={() => confirmAction({ title: `Supprimer ${p.is_credit_note ? "l'avoir" : "la facture"} ${p.invoice_number || "sans numéro"} ?`,
          message: deleteMessage(p), confirmLabel: "Supprimer", onConfirm: () => remove.mutate(p.id) })}>
        <Trash2 size={16} /></ActionIcon>
    ) },
  ];

  return (
    <>
      <PageHeader title="Factures d'achat" description="Factures fournisseurs reçues dans Qonto ou saisies dans l'application."
        actions={<>
          <Can><Button component={AppLink} href="/purchases/new">Nouvelle facture</Button>
          <Button variant="default" loading={sync.isPending} disabled={!meta?.qonto.available || shown?.status === "running"}
            onClick={() => sync.mutate(undefined, { onSuccess: (r) => setJob(r.job) })}>Synchroniser les factures Qonto</Button></Can>
        </>} />
      <IntegrationNotice name="qonto" state={meta?.qonto} consequence="synchronisation impossible" />
      {meta && (
        <Paper p="sm" mb="sm">
          <Group justify="space-between" gap="sm">
            <Text size="sm">Qonto : factures à partir du {formatDate(meta.sync.from)} · dernière synchronisation :{" "}
              {meta.sync.synced_at ? `${formatDate(meta.sync.synced_at)} à ${meta.sync.synced_at.slice(11, 16)}` : "jamais"}</Text>
            {can.instanceAdmin && <SyncFrom key={meta.sync.from} value={meta.sync.from} />}
          </Group>
        </Paper>
      )}
      {shown && <JobStatus key={shown.id} job={shown} renderResult={syncResult}
        onDone={() => void client.invalidateQueries({ queryKey: PURCHASES_KEY })} />}
      {!!counters?.to_replace && (
        <Alert color="brique" mb="sm">
          <Anchor component={AppLink} href="/purchases/settlements">{counters.to_replace} paiement(s) de facture déjà passé(s) en charge par une règle</Anchor>
          {" "}: la charge serait comptée deux fois, à remplacer par un règlement fournisseur.
        </Alert>
      )}
      {!!(counters && (counters.to_complete || counters.to_review || counters.supplier_proposals || counters.ready)) && (
        <Alert color="paille" mb="sm">
          <Group justify="space-between" gap="sm">
            <Group gap="md">
              {counters.to_complete > 0 && <Text size="sm"><Anchor component="button" size="sm" onClick={() => setParams({ state: "to_complete" })}>{counters.to_complete} facture(s) à compléter</Anchor>
                {counters.without_supplier > 0 && <> (dont <Anchor component="button" size="sm" onClick={() => setParams({ no_supplier: "1" })}>{counters.without_supplier} sans fournisseur rattaché</Anchor>)</>}.</Text>}
              {counters.supplier_proposals > 0 && <Anchor component={AppLink} href="/purchases/suppliers" size="sm" fw={600}>{counters.supplier_proposals} fournisseur(s) à valider</Anchor>}
              {counters.to_review > 0 && <Text size="sm" c="var(--lv-brique)">{counters.to_review} facture(s) comptabilisée(s) modifiée(s) dans Qonto, à revoir.</Text>}
            </Group>
            <Can>{counters.ready > 0 && <Button size="compact-md" variant="default" loading={postReady.isPending} onClick={() => postReady.mutate()}>
              Comptabiliser les factures prêtes ({counters.ready})</Button>}</Can>
          </Group>
        </Alert>
      )}
      <FilterBar>
        <SearchInput value={params.q} onChange={(q) => setParams({ q })} placeholder="Numéro, fournisseur…" />
        <Select label="État" placeholder="Tous" clearable data={meta?.states ?? []} value={params.state || null} onChange={(state) => setParams({ state: state ?? "" })} w={150} />
        <Select label="Statut Qonto" placeholder="Tous" clearable data={meta?.statuses ?? []} value={params.status || null} onChange={(status) => setParams({ status: status ?? "" })} w={160} />
        <Select label="Origine" placeholder="Toutes" clearable data={[{ value: "qonto", label: "Qonto" }, { value: "manual", label: "Saisies" }]}
          value={params.source || null} onChange={(source) => setParams({ source: source ?? "" })} w={120} />
        <Select label="Fournisseur" placeholder="Tous" clearable searchable data={meta?.suppliers ?? []} value={params.entity_id || null}
          onChange={(entity_id) => setParams({ entity_id: entity_id ?? "" })} w={200} />
        <MonthSelect value={params.month} onChange={(month) => setParams({ month })} options={meta?.months} />
        <Group gap="md" pb={8}>
          <Checkbox label="Non payées" checked={params.unpaid === "1"} onChange={(e) => setParams({ unpaid: e.currentTarget.checked ? "1" : "" })} />
          <Checkbox label="Sans fournisseur" checked={params.no_supplier === "1"} onChange={(e) => setParams({ no_supplier: e.currentTarget.checked ? "1" : "" })} />
          <Checkbox label={`Masquées (${counters?.hidden ?? 0})`} checked={params.hidden === "1"} onChange={(e) => setParams({ hidden: e.currentTarget.checked ? "1" : "" })} />
        </Group>
      </FilterBar>
      <DataGrid id="purchases" records={data?.items} columns={columns} fetching={isFetching}
        sort={{ column: "issue_date", direction: params.sort === "asc" ? "asc" : "desc" }} onSortChange={(s) => setParams({ sort: s.direction })}
        emptyText={filtered ? "Aucune facture d'achat pour ces critères." : "Aucune facture d'achat."} />
    </>
  );
}
