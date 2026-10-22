// Compta › Grand livre : lignes d'un compte avec solde cumulé.
import { Anchor, Select, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { useUrlParams } from "../../components/FilterBar";
import { MoneyText } from "../../components/Money";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { ReportFrame, type ReportMeta } from "./ReportFrame";

interface Row {
  entry_id: number; url: string; date: string; reference: string | null; journal: string; label: string;
  debit_cents: number; credit_cents: number; running_cents: number;
}
interface Response {
  account: { id: number; code: string; label: string } | null; items: Row[];
  meta: ReportMeta & { accounts: { value: string; label: string }[] };
}

const COLUMNS: GridColumn<Row>[] = [
  { accessor: "date", title: "Date", hideable: false, render: (r) => <span className="lv-num">{formatDate(r.date)}</span> },
  { accessor: "reference", title: "Référence",
    render: (r) => <Anchor component={AppLink} href={r.url} className="lv-num">{r.reference ?? `#${r.entry_id}`}</Anchor> },
  { accessor: "journal", title: "Journal", render: (r) => <span className="lv-num">{r.journal}</span> },
  { accessor: "label", title: "Libellé" },
  { accessor: "debit_cents", title: "Débit", textAlign: "right", render: (r) => (r.debit_cents ? <MoneyText cents={r.debit_cents} /> : null) },
  { accessor: "credit_cents", title: "Crédit", textAlign: "right", render: (r) => (r.credit_cents ? <MoneyText cents={r.credit_cents} /> : null) },
  { accessor: "running_cents", title: "Solde", textAlign: "right", hideable: false, render: (r) => <MoneyText cents={r.running_cents} fw={600} /> },
];

export default function GeneralLedgerPage() {
  const [params, setParams] = useUrlParams({ fy_id: "", account_id: "" });
  const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
  const { data, isFetching } = useQuery({
    queryKey: ["reports", "grand-livre", query], placeholderData: (prev) => prev,
    queryFn: () => api.get<Response>(`/api/v1/reports/grand-livre${query ? `?${query}` : ""}`),
  });
  return (
    <ReportFrame title="Grand livre" meta={data?.meta} fyId={params.fy_id} onFyChange={(fy_id) => setParams({ fy_id })} loading={isFetching}
      filters={<Select label="Compte" placeholder="Choisir un compte" searchable data={data?.meta.accounts ?? []} w={360}
        value={params.account_id || null} onChange={(v) => setParams({ account_id: v ?? "" })} nothingFoundMessage="Aucun compte" />}>
      {!params.account_id ? <Text c="dimmed">Choisissez un compte pour afficher ses mouvements.</Text> : (
        <DataGrid id="grand-livre" records={data?.items} columns={COLUMNS} fetching={isFetching} idAccessor="entry_id"
          toolbar={data?.account && <Text fw={600}><span className="lv-num">{data.account.code}</span> — {data.account.label}</Text>}
          emptyText="Aucun mouvement sur ce compte pour l'exercice." />
      )}
    </ReportFrame>
  );
}
