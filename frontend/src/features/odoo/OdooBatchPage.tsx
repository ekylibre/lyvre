// Imports › Lot Odoo : lignes importées, filtrées par mois, et leur écriture.
import { useParams } from "react-router";
import { Anchor, Button } from "@mantine/core";
import { useList } from "../../api/resources";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { MoneyText } from "../../components/Money";
import { MonthSelect, type MonthOption } from "../../components/MonthSelect";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { ODOO_IMPORTS_KEY } from "./types";

interface Line {
  id: number; invoice_number: string | null; date: string | null; partner: string | null; product: string | null;
  untaxed_cents: number; tax_cents: number; total_cents: number; account_code: string | null; entry_url: string | null;
}

const COLUMNS: GridColumn<Line>[] = [
  { accessor: "invoice_number", title: "Facture", hideable: false },
  { accessor: "date", title: "Date", sortable: true, render: (l) => <span className="lv-num">{formatDate(l.date)}</span> },
  { accessor: "partner", title: "Client" },
  { accessor: "product", title: "Produit" },
  { accessor: "untaxed_cents", title: "HT", textAlign: "right", render: (l) => <MoneyText cents={l.untaxed_cents} /> },
  { accessor: "tax_cents", title: "TVA", textAlign: "right", render: (l) => <MoneyText cents={l.tax_cents} /> },
  { accessor: "total_cents", title: "TTC", textAlign: "right", render: (l) => <MoneyText cents={l.total_cents} /> },
  { accessor: "account_code", title: "Compte", render: (l) => <span className="lv-num">{l.account_code}</span> },
  { accessor: "entry_url", title: "Écriture", render: (l) => l.entry_url
    ? <Anchor component={AppLink} href={l.entry_url}><StatusBadge tone="ok">Comptabilisé</StatusBadge></Anchor>
    : <StatusBadge tone="neutral">En attente</StatusBadge> },
];

export default function OdooBatchPage() {
  const batch = useParams().batch_name ?? "";
  const [params, setParams] = useUrlParams({ month: "", sort: "" });
  const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
  const { data, isFetching } = useList<Line, { batch: string; months: MonthOption[] }>([...ODOO_IMPORTS_KEY, batch],
    `/api/v1/imports/odoo/batches/${encodeURIComponent(batch)}${query ? `?${query}` : ""}`);
  return (
    <>
      <PageHeader title={`Lot Odoo : ${batch}`} actions={<Button variant="default" component={AppLink} href="/imports/odoo">Retour</Button>} />
      <FilterBar><MonthSelect value={params.month} onChange={(month) => setParams({ month })} options={data?.meta?.months} /></FilterBar>
      <DataGrid id="odoo-batch" records={data?.items} columns={COLUMNS} fetching={isFetching}
        sort={params.sort ? { column: "date", direction: params.sort === "asc" ? "asc" : "desc" } : null}
        onSortChange={(s) => setParams({ sort: s.direction })} emptyText="Aucune ligne dans ce lot." />
    </>
  );
}
