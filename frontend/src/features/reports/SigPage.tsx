// Compta › Soldes intermédiaires (exploitation agricole, lot AG1.c) : marge commerciale, production de l'exercice,
// valeur ajoutée, EBE et résultats, N et N-1 ; export tableur avec le tableau des biens vivants.
import { Button } from "@mantine/core";
import { Download } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useUrlParams } from "../../components/FilterBar";
import { ReportFrame, type ReportMeta } from "./ReportFrame";
import { StatementTable, type StatementLine } from "./StatementTable";

interface SigRow { key: string; label: string; kind: "row" | "total" | "result"; n: number; p: number | null }
interface Response { items: SigRow[]; meta: ReportMeta & { export_url: string | null } }

/** Composantes en retrait sous leur solde. */
const COMPONENTS = new Set(["consommations", "subventions", "impots_taxes", "charges_personnel"]);

export default function SigPage() {
  const [params, setParams] = useUrlParams({ fy_id: "" });
  const { data, isFetching } = useQuery({
    queryKey: ["reports", "sig", params.fy_id], placeholderData: (prev) => prev,
    queryFn: () => api.get<Response>(`/api/v1/reports/sig${params.fy_id ? `?fy_id=${params.fy_id}` : ""}`),
  });
  const meta = data?.meta;
  const lines: StatementLine[] = (data?.items ?? []).map((r) => ({
    kind: r.kind, label: r.label, n: r.n, p: r.p, indent: COMPONENTS.has(r.key) ? 1 : 0 }));
  return (
    <ReportFrame title="Soldes intermédiaires de gestion" meta={meta} fyId={params.fy_id}
      onFyChange={(fy_id) => setParams({ fy_id })} loading={isFetching}
      actions={meta?.export_url && <Button variant="default" component="a" href={meta.export_url}
        leftSection={<Download size={18} />}>Exporter en XLSX</Button>}>
      <StatementTable title="Solde" lines={lines}
        nLabel={`Exercice N${meta?.fiscal_year ? ` (${meta.fiscal_year.label})` : ""}`}
        pLabel={`Exercice N-1${meta?.previous ? ` (${meta.previous.label})` : ""}`} showPrevious={!!meta?.previous} />
    </ReportFrame>
  );
}
