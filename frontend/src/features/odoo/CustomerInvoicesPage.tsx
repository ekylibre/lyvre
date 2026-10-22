// Ventes › Factures clients : factures Odoo (account.move, out_invoice) synchronisées.
import { Anchor, Button, Select, Text } from "@mantine/core";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FilterBar, SearchInput, useUrlParams } from "../../components/FilterBar";
import { IntegrationNotice } from "../../components/IntegrationNotice";
import { MoneyText } from "../../components/Money";
import { MonthSelect } from "../../components/MonthSelect";
import { PageHeader } from "../../components/PageHeader";
import { Can } from "../../components/Can";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { INVOICES_KEY, INVOICE_TONES, PAYMENT_TONES, SYNC_HINT, type OdooMeta, type Option } from "./types";

export interface CustomerInvoice {
  id: number; number: string; ref: string | null; date: string | null; due_date: string | null; partner: string | null;
  entity_id: number | null; untaxed_cents: number; tax_cents: number; total_cents: number; residual_cents: number;
  state: string | null; state_label: string; payment_state: string | null; payment_state_label: string;
}

/** Reste dû d'une facture validée : en brique (relance à faire). */
export const isDue = (inv: CustomerInvoice) => inv.residual_cents > 0 && inv.state === "posted";

export function Partner({ inv }: { inv: CustomerInvoice }) {
  return inv.entity_id
    ? <Anchor component={AppLink} href={`/entities/${inv.entity_id}`} size="sm">{inv.partner ?? "—"}</Anchor>
    : <Text size="sm">{inv.partner ?? "—"}</Text>;
}

const COLUMNS: GridColumn<CustomerInvoice>[] = [
  { accessor: "date", title: "Date", sortable: true, hideable: false, render: (i) => <span className="lv-num">{formatDate(i.date)}</span> },
  { accessor: "number", title: "Numéro", hideable: false, render: (i) => <Anchor component={AppLink} href={`/customer-invoices/${i.id}`} size="sm" className="lv-num">{i.number}</Anchor> },
  { accessor: "ref", title: "Référence", render: (i) => <Text size="sm" c="dimmed">{i.ref ?? ""}</Text> },
  { accessor: "partner", title: "Client", render: (i) => <Partner inv={i} /> },
  { accessor: "untaxed_cents", title: "Total HT", textAlign: "right", render: (i) => <MoneyText cents={i.untaxed_cents} /> },
  { accessor: "tax_cents", title: "TVA", textAlign: "right", render: (i) => <MoneyText cents={i.tax_cents} c="dimmed" /> },
  { accessor: "total_cents", title: "Total TTC", textAlign: "right", render: (i) => <MoneyText cents={i.total_cents} /> },
  { accessor: "residual_cents", title: "Reste dû", textAlign: "right", render: (i) => <MoneyText cents={i.residual_cents} anomaly={isDue(i)} fw={isDue(i) ? 600 : undefined} c={isDue(i) ? undefined : "dimmed"} /> },
  { accessor: "state", title: "État", render: (i) => <StatusBadge tone={INVOICE_TONES[i.state ?? ""] ?? "neutral"}>{i.state_label}</StatusBadge> },
  { accessor: "payment_state", title: "Paiement", render: (i) => <StatusBadge tone={PAYMENT_TONES[i.payment_state ?? ""] ?? "neutral"}>{i.payment_state_label}</StatusBadge> },
];

export default function CustomerInvoicesPage() {
  const [params, setParams] = useUrlParams({ q: "", state: "", payment_state: "", month: "", sort: "desc" });
  const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
  const { data, isFetching } = useList<CustomerInvoice, OdooMeta & { states: Option[]; payment_states: Option[] }>(
    INVOICES_KEY, `/api/v1/customer-invoices${query ? `?${query}` : ""}`);
  const sync = useAction(() => api.post<{ notices: Notice[] }>("/api/v1/customer-invoices/sync"), { invalidate: [INVOICES_KEY] });
  const filtered = Boolean(params.q || params.state || params.payment_state || params.month);
  return (
    <>
      <PageHeader title="Factures clients" description="Factures Odoo (account.move · out_invoice) synchronisées."
        actions={<Can><Button loading={sync.isPending} disabled={!data?.meta?.odoo.available} title={SYNC_HINT}
          onClick={() => sync.mutate()}>Synchroniser depuis Odoo</Button></Can>} />
      <IntegrationNotice name="odoo" state={data?.meta?.odoo} consequence="synchronisation des factures indisponible" />
      <FilterBar>
        <SearchInput value={params.q} onChange={(q) => setParams({ q })} placeholder="Numéro, client, email…" />
        <Select label="État comptable" placeholder="Tous" clearable data={data?.meta?.states ?? []} value={params.state || null}
          onChange={(state) => setParams({ state: state ?? "" })} w={170} />
        <Select label="État paiement" placeholder="Tous" clearable data={data?.meta?.payment_states ?? []} value={params.payment_state || null}
          onChange={(payment_state) => setParams({ payment_state: payment_state ?? "" })} w={170} />
        <MonthSelect value={params.month} onChange={(month) => setParams({ month })} options={data?.meta?.months} />
      </FilterBar>
      <DataGrid id="customer-invoices" records={data?.items} columns={COLUMNS} fetching={isFetching}
        sort={{ column: "date", direction: params.sort === "asc" ? "asc" : "desc" }} onSortChange={(s) => setParams({ sort: s.direction })}
        emptyText={filtered ? "Aucune facture pour ces critères." : "Aucune facture importée pour le moment."} />
    </>
  );
}
