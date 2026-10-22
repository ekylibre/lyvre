// Ventes › Commandes POS : commandes Odoo (pos.order) synchronisées, par mois.
import { Anchor, Button, Text } from "@mantine/core";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { IntegrationNotice } from "../../components/IntegrationNotice";
import { MoneyText } from "../../components/Money";
import { MonthSelect } from "../../components/MonthSelect";
import { PageHeader } from "../../components/PageHeader";
import { Can } from "../../components/Can";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDateTime } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { ORDERS_KEY, ORDER_TONES, SYNC_HINT, type OdooMeta } from "./types";

interface Order {
  id: number; reference: string; date: string | null; session: string | null; partner: string | null;
  total_cents: number; tax_cents: number; paid_cents: number; lines: number; payments: number;
  state: string | null; state_label: string;
}

const COLUMNS: GridColumn<Order>[] = [
  { accessor: "date", title: "Date", sortable: true, hideable: false, render: (o) => <span className="lv-num">{formatDateTime(o.date)}</span> },
  { accessor: "reference", title: "Référence", hideable: false, render: (o) => <Anchor component={AppLink} href={`/orders/${o.id}`} size="sm" className="lv-num">{o.reference}</Anchor> },
  { accessor: "session", title: "Session", render: (o) => <Text size="sm" c="dimmed">{o.session ?? "—"}</Text> },
  { accessor: "partner", title: "Client" },
  { accessor: "total_cents", title: "Total TTC", textAlign: "right", render: (o) => <MoneyText cents={o.total_cents} /> },
  { accessor: "tax_cents", title: "TVA", textAlign: "right", render: (o) => <MoneyText cents={o.tax_cents} c="dimmed" /> },
  { accessor: "paid_cents", title: "Payé", textAlign: "right", render: (o) => <MoneyText cents={o.paid_cents} /> },
  { accessor: "lines", title: "Lignes", textAlign: "right", render: (o) => <span className="lv-num">{o.lines}</span> },
  { accessor: "payments", title: "Paiements", textAlign: "right", render: (o) => <span className="lv-num">{o.payments}</span> },
  { accessor: "state", title: "Statut", render: (o) => <StatusBadge tone={ORDER_TONES[o.state ?? ""] ?? "neutral"}>{o.state_label}</StatusBadge> },
];

export default function OrdersPage() {
  const [params, setParams] = useUrlParams({ month: "", sort: "desc" });
  const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
  const { data, isFetching } = useList<Order, OdooMeta>(ORDERS_KEY, `/api/v1/orders${query ? `?${query}` : ""}`);
  const sync = useAction(() => api.post<{ notices: Notice[] }>("/api/v1/orders/sync"), { invalidate: [ORDERS_KEY] });
  const count = data?.items.length ?? 0;
  return (
    <>
      <PageHeader title="Commandes point de vente" description="Commandes Odoo (pos.order) synchronisées."
        actions={<Can><Button loading={sync.isPending} disabled={!data?.meta?.odoo.available} title={SYNC_HINT}
          onClick={() => sync.mutate()}>Synchroniser depuis Odoo</Button></Can>} />
      <IntegrationNotice name="odoo" state={data?.meta?.odoo} consequence="synchronisation des commandes indisponible" />
      <FilterBar><MonthSelect value={params.month} onChange={(month) => setParams({ month })} options={data?.meta?.months} /></FilterBar>
      <DataGrid id="orders" records={data?.items} columns={COLUMNS} fetching={isFetching}
        sort={{ column: "date", direction: params.sort === "asc" ? "asc" : "desc" }} onSortChange={(s) => setParams({ sort: s.direction })}
        toolbar={count >= (data?.meta?.limit ?? Infinity) ? <Text size="sm" c="dimmed">Limite d'affichage : {count} commandes.</Text> : undefined}
        emptyText="Aucune commande importée pour le moment." />
    </>
  );
}
