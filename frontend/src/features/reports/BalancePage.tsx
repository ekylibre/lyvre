// Compta › Balance : mouvements et soldes par compte sur l'exercice.
import { Text } from "@mantine/core";
import { useList } from "../../api/resources";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { useUrlParams } from "../../components/FilterBar";
import { MoneyText } from "../../components/Money";
import { ReportFrame, type ReportMeta } from "./ReportFrame";

interface Row {
  account_id: number; code: string; label: string; debit_cents: number; credit_cents: number;
  balance_debit_cents: number; balance_credit_cents: number;
}

const money = (key: keyof Row, title: string, hideEmpty = false): GridColumn<Row> => ({
  accessor: key, title, textAlign: "right", sortable: true,
  render: (r) => (hideEmpty && !r[key] ? null : <MoneyText cents={r[key] as number} />),
});

const COLUMNS: GridColumn<Row>[] = [
  { accessor: "code", title: "Compte", sortable: true, hideable: false, render: (r) => <span className="lv-num">{r.code}</span> },
  { accessor: "label", title: "Libellé", sortable: true },
  money("debit_cents", "Débit"), money("credit_cents", "Crédit"),
  money("balance_debit_cents", "Solde débiteur", true), money("balance_credit_cents", "Solde créditeur", true),
];

export default function BalancePage() {
  const [params, setParams] = useUrlParams({ fy_id: "" });
  const { data, isFetching } = useList<Row, ReportMeta>(["reports", "balance"],
    `/api/v1/reports/balance${params.fy_id ? `?fy_id=${params.fy_id}` : ""}`);
  const rows = data?.items ?? [];
  const sum = (key: keyof Row) => rows.reduce((s, r) => s + (r[key] as number), 0);
  return (
    <ReportFrame title="Balance" meta={data?.meta} fyId={params.fy_id} onFyChange={(fy_id) => setParams({ fy_id })} loading={isFetching}>
      <DataGrid id="balance" records={rows} columns={COLUMNS} fetching={isFetching} idAccessor="account_id"
        defaultSort={{ column: "code", direction: "asc" }} emptyText="Aucun mouvement sur l'exercice."
        toolbar={<Text size="sm">Total débit <MoneyText cents={sum("debit_cents")} fw={600} /> · crédit{" "}
          <MoneyText cents={sum("credit_cents")} fw={600} /></Text>} />
    </ReportFrame>
  );
}
