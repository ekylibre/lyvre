// Compta › Bilan : actif et passif, exercice N et N-1.
import { SimpleGrid } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useUrlParams } from "../../components/FilterBar";
import { ReportFrame, type ReportMeta } from "./ReportFrame";
import { StatementTable, type StatementLine } from "./StatementTable";

interface Response { actif: StatementLine[]; passif: StatementLine[]; meta: ReportMeta }

export default function BilanPage() {
  const [params, setParams] = useUrlParams({ fy_id: "" });
  const { data, isFetching } = useQuery({
    queryKey: ["reports", "bilan", params.fy_id], placeholderData: (prev) => prev,
    queryFn: () => api.get<Response>(`/api/v1/reports/bilan${params.fy_id ? `?fy_id=${params.fy_id}` : ""}`),
  });
  const prev = !!data?.meta.previous;
  return (
    <ReportFrame title="Bilan" meta={data?.meta} fyId={params.fy_id} onFyChange={(fy_id) => setParams({ fy_id })} loading={isFetching}>
      <SimpleGrid cols={{ base: 1, lg: 2 }}>
        <StatementTable title="Actif" lines={data?.actif ?? []} nLabel="Net N" pLabel="Net N-1" showPrevious={prev} />
        <StatementTable title="Passif" lines={data?.passif ?? []} nLabel="N" pLabel="N-1" showPrevious={prev} />
      </SimpleGrid>
    </ReportFrame>
  );
}
