// Compta › Budget › Suivi : prévu (année, à date), réalisé à date et écart par poste, budget
// général ou d'un projet ; réalisé hors budget ; graphique des charges ; export tableur.
import { Badge, Button, Center, Group, Loader, Paper, Progress, Select, SimpleGrid, Table, Text, Title } from "@mantine/core";
import { BarChart } from "@mantine/charts";
import { DateInput } from "@mantine/dates";
import { useQuery } from "@tanstack/react-query";
import { Download, Printer } from "lucide-react";
import { api } from "../../api/client";
import { useList } from "../../api/resources";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { formatDate, formatEuros } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { FISCAL_YEARS_KEY, type FiscalYear } from "../fiscal-years/FiscalYearsPage";

interface TrackingRow {
  code: string; label: string; kind: "expense" | "income"; unbudgeted: boolean; planned_cents: number;
  planned_to_date_cents: number; actual_cents: number; gap_cents: number; rate: number | null;
}
type Figures = { planned_cents: number; planned_to_date_cents: number; actual_cents: number; gap_cents?: number };
export interface Tracking {
  fiscal_year: { id: number; label: string }; project_id: number | null; projects: { value: string; label: string }[];
  as_of: string; elapsed_months: number; months: number; rows: TrackingRow[]; export_url: string;
  summary: { expense: Figures; income: Figures; result: Figures };
}

/** Un écart est défavorable si les charges dépassent ou si les produits manquent. */
const unfavourable = (kind: TrackingRow["kind"], gap: number) => (kind === "expense" ? gap > 0 : gap < 0);

export function useTracking(fyId: string, projectId = "", asOf = "") {
  const query = `/api/v1/budgets/${fyId}/tracking?project_id=${projectId}${asOf ? `&as_of=${asOf}` : ""}`;
  return useQuery({ queryKey: ["budgets", "tracking", query], enabled: !!fyId, placeholderData: (prev) => prev,
    queryFn: () => api.get<Tracking>(query) });
}

export function RateBar({ row }: { row: Pick<TrackingRow, "kind" | "rate" | "gap_cents"> }) {
  if (row.rate === null) return <Text size="xs" c="dimmed">—</Text>;
  const bad = unfavourable(row.kind, row.gap_cents);
  return (
    <Group gap="xs" wrap="nowrap">
      <Progress value={Math.min(row.rate, 100)} w={80} color={bad ? "brique" : "lichen"} aria-hidden />
      <Text size="sm" className="lv-num" c={bad ? "var(--lv-brique)" : undefined}>{row.rate.toLocaleString("fr-FR")} %</Text>
    </Group>
  );
}

export default function BudgetTrackingPage() {
  const years = useList<FiscalYear>(FISCAL_YEARS_KEY, "/api/v1/fiscal-years");
  const [params, setParams] = useUrlParams({ fiscal_year_id: "", project_id: "", as_of: "" });
  const defaultYear = years.data?.items.find((fy) => fy.status === "open") ?? years.data?.items[0];
  const fyId = params.fiscal_year_id || (defaultYear ? String(defaultYear.id) : "");
  const { data } = useTracking(fyId, params.project_id, params.as_of);
  const sections = [
    { kind: "expense" as const, title: "Charges" },
    { kind: "income" as const, title: "Produits" },
  ];
  const chart = (data?.rows ?? []).filter((r) => r.kind === "expense" && !r.unbudgeted)
    .map((r) => ({ poste: r.code, "Prévu à date": r.planned_to_date_cents / 100, "Réalisé": r.actual_cents / 100 }));
  return (
    <>
      <PageHeader title="Suivi budgétaire"
        description={data ? `Exercice ${data.fiscal_year.label} · au ${formatDate(data.as_of)} (${data.elapsed_months} mois sur ${data.months})` : undefined}
        actions={<>
          <Button variant="default" component={AppLink} href={`/budget/?fiscal_year_id=${fyId}&project_id=${params.project_id}`}>Saisir le budget</Button>
          {data && <Button variant="default" component="a" href={data.export_url} leftSection={<Download size={16} />}>Exporter (XLSX)</Button>}
          <Button variant="default" leftSection={<Printer size={16} />} onClick={() => window.print()}>Imprimer</Button>
        </>} />
      <FilterBar>
        <Select aria-label="Exercice" w={180} allowDeselect={false} value={fyId || null}
          data={(years.data?.items ?? []).map((fy) => ({ value: String(fy.id), label: `Exercice ${fy.label}` }))}
          onChange={(v) => setParams({ ...params, fiscal_year_id: v ?? "", as_of: "" })} />
        <Select aria-label="Projet" w={240} placeholder="Budget général" clearable value={params.project_id || null}
          data={data?.projects ?? []} onChange={(v) => setParams({ ...params, project_id: v ?? "" })} />
        <DateInput aria-label="Situation au" w={160} valueFormat="DD/MM/YYYY" value={params.as_of || data?.as_of || null}
          onChange={(v) => setParams({ ...params, as_of: v ?? "" })} />
      </FilterBar>
      {!data ? <Center h={200}><Loader /></Center> : (
        <>
          <SimpleGrid cols={{ base: 1, sm: 3 }} mb="md">
            {sections.map((s) => (
              <Paper p="md" key={s.kind}>
                <Text size="sm" c="dimmed">{s.title} réalisées / prévues à date</Text>
                <Text fz={24} fw={500} className="lv-num"><MoneyText cents={data.summary[s.kind].actual_cents} /></Text>
                <Text size="sm" c="dimmed">sur <MoneyText cents={data.summary[s.kind].planned_to_date_cents} size="sm" /> · année <MoneyText cents={data.summary[s.kind].planned_cents} size="sm" /></Text>
              </Paper>
            ))}
            <Paper p="md">
              <Text size="sm" c="dimmed">Résultat réalisé / prévu à date</Text>
              <Text fz={24} fw={500} className="lv-num"><MoneyText cents={data.summary.result.actual_cents} anomaly={data.summary.result.actual_cents < 0} /></Text>
              <Text size="sm" c="dimmed">prévu <MoneyText cents={data.summary.result.planned_to_date_cents} size="sm" /></Text>
            </Paper>
          </SimpleGrid>
          {chart.length > 0 && (
            <Paper p="md" mb="md" className="lv-no-print">
              <Title order={2} size="h4" mb="sm">Charges : prévu à date et réalisé</Title>
              <BarChart h={240} data={chart} dataKey="poste" valueFormatter={(v) => formatEuros(Math.round(v * 100))} withLegend
                series={[{ name: "Prévu à date", color: "var(--lv-ardoise)" }, { name: "Réalisé", color: "var(--lv-lichen)" }]} />
            </Paper>
          )}
          <Paper p={0} style={{ overflowX: "auto" }}>
            <Table verticalSpacing={6} miw={760}>
              <Table.Thead bg="var(--lv-sauge)">
                <Table.Tr><Table.Th>Poste</Table.Th><Table.Th ta="right">Prévu (année)</Table.Th><Table.Th ta="right">Prévu à date</Table.Th>
                  <Table.Th ta="right">Réalisé</Table.Th><Table.Th ta="right">Écart</Table.Th><Table.Th>Réalisé / prévu</Table.Th></Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {sections.map((s) => {
                  const rows = data.rows.filter((r) => r.kind === s.kind);
                  const total = data.summary[s.kind];
                  return [
                    <Table.Tr key={`${s.kind}-h`}><Table.Td colSpan={6}><Text fw={700} size="sm">{s.title}</Text></Table.Td></Table.Tr>,
                    ...rows.map((r) => (
                      <Table.Tr key={`${s.kind}-${r.code}`}>
                        <Table.Td><Text size="sm"><span className="lv-num">{r.code}</span> <Text span size="sm" c="dimmed">{r.label}</Text>
                          {r.unbudgeted && <Badge ml="xs" size="xs" variant="light" color="paille">hors budget</Badge>}</Text></Table.Td>
                        <Table.Td ta="right"><MoneyText cents={r.planned_cents} size="sm" /></Table.Td>
                        <Table.Td ta="right"><MoneyText cents={r.planned_to_date_cents} size="sm" /></Table.Td>
                        <Table.Td ta="right"><MoneyText cents={r.actual_cents} size="sm" fw={600} /></Table.Td>
                        <Table.Td ta="right"><MoneyText cents={r.gap_cents} size="sm" plus anomaly={unfavourable(r.kind, r.gap_cents)} /></Table.Td>
                        <Table.Td><RateBar row={r} /></Table.Td>
                      </Table.Tr>
                    )),
                    <Table.Tr key={`${s.kind}-t`}>
                      <Table.Td><Text size="sm" fw={600}>Total {s.title.toLowerCase()}</Text></Table.Td>
                      <Table.Td ta="right"><MoneyText cents={total.planned_cents} fw={600} size="sm" /></Table.Td>
                      <Table.Td ta="right"><MoneyText cents={total.planned_to_date_cents} fw={600} size="sm" /></Table.Td>
                      <Table.Td ta="right"><MoneyText cents={total.actual_cents} fw={700} size="sm" /></Table.Td>
                      <Table.Td ta="right"><MoneyText cents={total.gap_cents ?? 0} plus size="sm" fw={600} anomaly={unfavourable(s.kind, total.gap_cents ?? 0)} /></Table.Td>
                      <Table.Td />
                    </Table.Tr>,
                  ];
                })}
              </Table.Tbody>
            </Table>
          </Paper>
          {data.rows.length === 0 && <Text size="sm" c="dimmed" mt="sm">Ni budget ni réalisé sur ce périmètre.</Text>}
          <Text size="xs" c="dimmed" mt="md" className="lv-print-only">Imprimé le {new Date().toLocaleDateString("fr-FR")}</Text>
        </>
      )}
    </>
  );
}
