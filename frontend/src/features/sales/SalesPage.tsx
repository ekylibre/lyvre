// Ventes : factures et avoirs de l'application ; filtres (type, état, client, mois, échues),
// totaux des pièces émises, envoi par email d'une sélection (SMTP).
import { useState } from "react";
import { Anchor, Badge, Button, Checkbox, Group, SegmentedControl, Select, Text } from "@mantine/core";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { Can } from "../../components/Can";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FilterBar, SearchInput, useUrlParams } from "../../components/FilterBar";
import { useIntegrationGuard } from "../../components/IntegrationRequired";
import { MoneyText } from "../../components/Money";
import { MonthSelect, type MonthOption } from "../../components/MonthSelect";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import type { Option } from "../purchases/types";
import { SALES_KEY, STATUS_TONES, type SaleRow } from "./types";

const FILTERS = { q: "", kind: "", status: "", entity_id: "", month: "", overdue: "" };
interface Meta { statuses: Option[]; clients: Option[]; months: MonthOption[]; totals: { untaxed_cents: number; total_cents: number }; drafts: number }

export default function SalesPage() {
  const [params, setParams] = useUrlParams(FILTERS);
  const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
  const { data, isFetching } = useList<SaleRow, Meta>(SALES_KEY, `/api/v1/sales${query ? `?${query}` : ""}`);
  const [selected, setSelected] = useState<SaleRow[]>([]);
  const smtp = useIntegrationGuard("smtp", "L'envoi par email");
  const send = useAction((ids: number[]) => api.post<{ notices: Notice[] }>("/api/v1/sales/send", { ids }), { invalidate: [SALES_KEY] });
  const meta = data?.meta;
  const sendable = selected.filter((s) => s.status !== "draft");

  const columns: GridColumn<SaleRow>[] = [
    { accessor: "issue_date", title: "Date", hideable: false, render: (s) => <span className="lv-num">{formatDate(s.issue_date)}</span> },
    { accessor: "number", title: "Numéro", hideable: false, render: (s) => (
      <Group gap={6} wrap="nowrap">
        <Anchor component={AppLink} href={`/sales/${s.id}`} size="sm" className="lv-num">{s.number ?? "brouillon"}</Anchor>
        {s.kind === "credit_note" && <Badge size="xs" variant="light" color="gray">Avoir</Badge>}
      </Group>
    ) },
    { accessor: "client", title: "Client", render: (s) => <Anchor component={AppLink} href={`/entities/${s.client.id}`} size="sm">{s.client.name}</Anchor> },
    { accessor: "untaxed_cents", title: "HT", textAlign: "right", render: (s) => <MoneyText cents={s.kind === "credit_note" ? -s.untaxed_cents : s.untaxed_cents} size="sm" /> },
    { accessor: "total_cents", title: "TTC", textAlign: "right", render: (s) => <MoneyText cents={s.kind === "credit_note" ? -s.total_cents : s.total_cents} size="sm" /> },
    { accessor: "status", title: "État", render: (s) => (
      <Group gap={6} wrap="nowrap"><StatusBadge tone={STATUS_TONES[s.status]}>{s.status_label}</StatusBadge>
        {s.overdue && <StatusBadge tone="gap">échue</StatusBadge>}</Group>
    ) },
    { accessor: "due_date", title: "Échéance", render: (s) => <span className="lv-num">{formatDate(s.due_date)}</span> },
    { accessor: "sent_at", title: "Envoyée", render: (s) => <Text size="sm" c="dimmed">{s.sent_at ? formatDate(s.sent_at) : ""}</Text> },
  ];

  return (
    <>
      <PageHeader title="Ventes" description="Factures et avoirs émis par l'application : numérotés, comptabilisés au journal des ventes, PDF Factur-X."
        actions={<Can><Button component={AppLink} href="/sales/new">Nouvelle facture</Button></Can>} />
      <FilterBar>
        <SegmentedControl value={params.kind} onChange={(kind) => setParams({ kind })}
          data={[{ value: "", label: "Tout" }, { value: "invoice", label: "Factures" }, { value: "credit_note", label: "Avoirs" }]} />
        <SearchInput value={params.q} onChange={(q) => setParams({ q })} placeholder="Numéro, client…" />
        <Select label="État" placeholder="Tous" clearable data={meta?.statuses ?? []} value={params.status || null}
          onChange={(status) => setParams({ status: status ?? "" })} w={160} />
        <Select label="Client" placeholder="Tous" clearable searchable data={meta?.clients ?? []} value={params.entity_id || null}
          onChange={(entity_id) => setParams({ entity_id: entity_id ?? "" })} w={200} />
        <MonthSelect value={params.month} onChange={(month) => setParams({ month })} options={meta?.months} />
        <Checkbox label="Échues" pb={8} checked={params.overdue === "1"} onChange={(e) => setParams({ overdue: e.currentTarget.checked ? "1" : "" })} />
      </FilterBar>
      {meta && <Group gap="lg" mb="sm">
        <Text size="sm">Émis (période filtrée) : <MoneyText cents={meta.totals.untaxed_cents} size="sm" /> HT · <MoneyText cents={meta.totals.total_cents} size="sm" /> TTC</Text>
        {meta.drafts > 0 && <Text size="sm" c="dimmed">{meta.drafts} brouillon(s)</Text>}
      </Group>}
      <DataGrid id="sales" records={data?.items} columns={columns} fetching={isFetching}
        emptyText="Aucune facture : créez la première."
        selection={{
          selected, onChange: setSelected,
          actions: () => <Button size="compact-sm" disabled={!sendable.length} loading={send.isPending}
            onClick={smtp.guard(() => send.mutate(sendable.map((s) => s.id), { onSuccess: () => setSelected([]) }))}>
            Envoyer par email ({sendable.length})</Button>,
        }} />
    </>
  );
}
