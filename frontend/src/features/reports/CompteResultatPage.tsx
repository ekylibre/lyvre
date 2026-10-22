// Compta › Compte de résultat : produits, charges, résultats, N et N-1 ; exports CSV / ODS.
import { Button } from "@mantine/core";
import { Download } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useUrlParams } from "../../components/FilterBar";
import { ReportFrame, type ReportMeta } from "./ReportFrame";
import { StatementTable, type StatementLine } from "./StatementTable";

interface Response { items: StatementLine[]; meta: ReportMeta & { export_urls: { csv: string; ods: string } | null } }

export default function CompteResultatPage() {
  const [params, setParams] = useUrlParams({ fy_id: "" });
  const { data, isFetching } = useQuery({
    queryKey: ["reports", "cdr", params.fy_id], placeholderData: (prev) => prev,
    queryFn: () => api.get<Response>(`/api/v1/reports/compte-de-resultat${params.fy_id ? `?fy_id=${params.fy_id}` : ""}`),
  });
  const meta = data?.meta;
  const exports = meta?.export_urls;
  return (
    <ReportFrame title="Compte de résultat" meta={meta} fyId={params.fy_id} onFyChange={(fy_id) => setParams({ fy_id })}
      loading={isFetching}
      actions={exports && <>
        <Button variant="default" component="a" href={exports.csv} leftSection={<Download size={18} />}>Exporter en CSV</Button>
        <Button variant="default" component="a" href={exports.ods} leftSection={<Download size={18} />}>Exporter en ODS</Button>
      </>}>
      <StatementTable title="Compte de résultat" lines={data?.items ?? []}
        nLabel={`Exercice N${meta?.fiscal_year ? ` (${meta.fiscal_year.label})` : ""}`}
        pLabel={`Exercice N-1${meta?.previous ? ` (${meta.previous.label})` : ""}`} showPrevious={!!meta?.previous} />
    </ReportFrame>
  );
}
