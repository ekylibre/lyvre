// Ventes : factures et avoirs de l'application ; filtres (type, état, client, mois, échues),
// totaux des pièces émises, restant dû ; envoi et relance par email d'une sélection (SMTP) ;
// rapprochement automatique des encaissements (crédit unique du montant restant dû).
import { useState } from "react";
import { Anchor, Badge, Button, Checkbox, Group, SegmentedControl, Select, Text } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { useIntegration } from "../../api/session";
import { Can } from "../../components/Can";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FilterBar, SearchInput, useUrlParams } from "../../components/FilterBar";
import { useIntegrationGuard } from "../../components/IntegrationRequired";
import { IntegrationNotice } from "../../components/IntegrationNotice";
import { JobStatus, type Job } from "../../components/JobStatus";
import { MoneyText } from "../../components/Money";
import { MonthSelect, type MonthOption } from "../../components/MonthSelect";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import type { Option } from "../purchases/types";
import { SALES_KEY, STATUS_TONES, type SaleRow } from "./types";

const FILTERS = { q: "", kind: "", status: "", entity_id: "", month: "", overdue: "" };
interface Meta { statuses: Option[]; clients: Option[]; months: MonthOption[];
  qonto?: { enabled: boolean; available: boolean; message: string | null; job: Job | null }; totals: { untaxed_cents: number; total_cents: number }; drafts: number }

export default function SalesPage() {
  const [params, setParams] = useUrlParams(FILTERS);
  const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
  const { data, isFetching } = useList<SaleRow, Meta>(SALES_KEY, `/api/v1/sales${query ? `?${query}` : ""}`);
  const [selected, setSelected] = useState<SaleRow[]>([]);
  const smtp = useIntegrationGuard("smtp", "L'envoi par email");
  const send = useAction((ids: number[]) => api.post<{ notices: Notice[] }>("/api/v1/sales/send", { ids }), { invalidate: [SALES_KEY] });
  const remind = useAction((ids: number[]) => api.post<{ notices: Notice[] }>("/api/v1/sales/remind", { ids }), { invalidate: [SALES_KEY] });
  const qontoSales = useIntegration("qonto", "sales");
  const client = useQueryClient();
  const [job, setJob] = useState<Job | null>(null);
  const shownJob = qontoSales ? job ?? data?.meta?.qonto?.job ?? null : null;
  const sync = useAction<void, { job: Job; notices?: Notice[] }>(() => api.post("/api/v1/sales/sync"));
  const autoMatch = useAction(() => api.post<{ notices: Notice[] }>("/api/v1/sales/auto-match"), { invalidate: [SALES_KEY] });
  const meta = data?.meta;
  const sendable = selected.filter((s) => s.status !== "draft");
  const remindable = selected.filter((s) => s.kind === "invoice" && s.due_cents > 0 && s.overdue);

  const quotes = params.kind === "quote";
  const invoiceColumns: GridColumn<SaleRow>[] = quotes ? [
    { accessor: "validity_date", title: "Valable jusqu'au", render: (s) => <span className="lv-num">{formatDate(s.validity_date)}</span> },
  ] : [
    { accessor: "due_cents", title: "Restant dû", textAlign: "right", render: (s) => s.kind === "invoice" && s.status !== "draft"
      ? <MoneyText cents={s.due_cents} size="sm" anomaly={s.overdue && s.due_cents > 0} /> : null },
    { accessor: "due_date", title: "Échéance", render: (s) => <span className="lv-num">{formatDate(s.due_date)}</span> },
    { accessor: "reminder_count", title: "Relances", render: (s) => s.reminder_count
      ? <Text size="sm" c="dimmed">{s.reminder_count} (le {formatDate(s.last_reminder_at)})</Text> : null },
  ];
  const columns: GridColumn<SaleRow>[] = [
    { accessor: "issue_date", title: "Date", hideable: false, render: (s) => <span className="lv-num">{formatDate(s.issue_date)}</span> },
    { accessor: "number", title: "Numéro", hideable: false, render: (s) => (
      <Group gap={6} wrap="nowrap">
        <Anchor component={AppLink} href={`/sales/${s.id}`} size="sm" className="lv-num">{s.number ?? "brouillon"}</Anchor>
        {s.kind === "credit_note" && <Badge size="xs" variant="light" color="gray">Avoir</Badge>}
        {qontoSales && (s.qonto_emit || s.source === "qonto") && <Badge size="xs" variant="outline" color="gray">Qonto</Badge>}
        {qontoSales && s.qonto_error && <Badge size="xs" color="brique" title={s.qonto_error}>Qonto : à revoir</Badge>}
      </Group>
    ) },
    { accessor: "client", title: "Client", render: (s) => <Anchor component={AppLink} href={`/entities/${s.client.id}`} size="sm">{s.client.name}</Anchor> },
    { accessor: "untaxed_cents", title: "HT", textAlign: "right", render: (s) => <MoneyText cents={s.kind === "credit_note" ? -s.untaxed_cents : s.untaxed_cents} size="sm" /> },
    { accessor: "total_cents", title: "TTC", textAlign: "right", render: (s) => <MoneyText cents={s.kind === "credit_note" ? -s.total_cents : s.total_cents} size="sm" /> },
    { accessor: "status", title: "État", render: (s) => (
      <Group gap={6} wrap="nowrap"><StatusBadge tone={STATUS_TONES[s.status]}>{s.status_label}</StatusBadge>
        {s.overdue && <StatusBadge tone="gap">échue</StatusBadge>}</Group>
    ) },
    ...invoiceColumns,
    { accessor: "sent_at", title: "Envoyé(e)", render: (s) => <Text size="sm" c="dimmed">{s.sent_at ? formatDate(s.sent_at) : ""}</Text> },
  ];

  return (
    <>
      <PageHeader title="Ventes" description={quotes ? "Devis : numérotés à l'émission, acceptés ou refusés, transformés en facture."
        : "Factures et avoirs émis par l'application : numérotés, comptabilisés au journal des ventes, PDF Factur-X."}
        actions={<Can>
          {qontoSales && <Button variant="default" loading={sync.isPending} disabled={!meta?.qonto?.available || shownJob?.status === "running"}
            onClick={() => sync.mutate(undefined, { onSuccess: (r) => setJob(r.job) })}>Synchroniser Qonto</Button>}
          <Button variant="default" loading={autoMatch.isPending} onClick={() => autoMatch.mutate()}
            title="Encaisse les factures dont un crédit bancaire unique a le montant exact du restant dû">Rapprocher les encaissements</Button>
          <Button variant={quotes ? "filled" : "default"} component={AppLink} href="/sales/new?kind=quote">Nouveau devis</Button>
          {!quotes && <Button component={AppLink} href="/sales/new">Nouvelle facture</Button>}</Can>} />
      <IntegrationNotice name="qonto" state={meta?.qonto} consequence="synchronisation des ventes impossible" />
      {shownJob && <JobStatus key={shownJob.id} job={shownJob} onDone={() => void client.invalidateQueries({ queryKey: SALES_KEY })} />}
      <FilterBar>
        <SegmentedControl value={params.kind} onChange={(kind) => setParams({ kind, status: "", overdue: "" })}
          data={[{ value: "", label: "Factures et avoirs" }, { value: "invoice", label: "Factures" }, { value: "credit_note", label: "Avoirs" },
            { value: "quote", label: "Devis" }]} />
        <SearchInput value={params.q} onChange={(q) => setParams({ q })} placeholder="Numéro, client…" />
        <Select label="État" placeholder="Tous" clearable data={meta?.statuses ?? []} value={params.status || null}
          onChange={(status) => setParams({ status: status ?? "" })} w={160} />
        <Select label="Client" placeholder="Tous" clearable searchable data={meta?.clients ?? []} value={params.entity_id || null}
          onChange={(entity_id) => setParams({ entity_id: entity_id ?? "" })} w={200} />
        <MonthSelect value={params.month} onChange={(month) => setParams({ month })} options={meta?.months} />
        {!quotes && <Checkbox label="Échues" pb={8} checked={params.overdue === "1"} onChange={(e) => setParams({ overdue: e.currentTarget.checked ? "1" : "" })} />}
      </FilterBar>
      {meta && <Group gap="lg" mb="sm">
        <Text size="sm">Émis (période filtrée) : <MoneyText cents={meta.totals.untaxed_cents} size="sm" /> HT · <MoneyText cents={meta.totals.total_cents} size="sm" /> TTC</Text>
        {meta.drafts > 0 && <Text size="sm" c="dimmed">{meta.drafts} brouillon(s)</Text>}
      </Group>}
      <DataGrid id="sales" records={data?.items} columns={columns} fetching={isFetching}
        emptyText={quotes ? "Aucun devis." : "Aucune facture : créez la première."}
        selection={{
          selected, onChange: setSelected,
          actions: () => <>
            <Button size="compact-sm" disabled={!sendable.length} loading={send.isPending}
              onClick={smtp.guard(() => send.mutate(sendable.map((s) => s.id), { onSuccess: () => setSelected([]) }))}>
              Envoyer par email ({sendable.length})</Button>
            <Button size="compact-sm" variant="default" disabled={!remindable.length} loading={remind.isPending}
              title="Factures échues non soldées de la sélection"
              onClick={smtp.guard(() => remind.mutate(remindable.map((s) => s.id), { onSuccess: () => setSelected([]) }))}>
              Relancer ({remindable.length})</Button>
          </>,
        }} />
    </>
  );
}
