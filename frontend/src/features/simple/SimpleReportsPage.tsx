// États (comptabilité simplifiée) : compte de résultat par catégorie (N / N-1) et situation de
// trésorerie (soldes début / fin d'exercice cumulés des comptes bancaires et caisses) ; impression.
import { Button, Center, Loader, Paper, Select, SimpleGrid, Table, Tabs, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Printer } from "lucide-react";
import { api } from "../../api/client";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { formatDate } from "../../lib/format";
import { useCurrentSession } from "../../api/session";
import { MicroBaSummary, ReceiptsBook, YearSelect } from "./MicroBaPanels";

type Option = { value: string; label: string };
interface Statement {
  fiscal_year_id: number; fiscal_years: Option[]; fiscal_year: string; previous_year: string | null;
  rows: { label: string; kind: "income" | "expense"; amount_cents: number; previous_cents: number }[];
  totals: Record<"income" | "expense", { amount_cents: number; previous_cents: number }>;
  result: { amount_cents: number; previous_cents: number };
}
interface Treasury {
  fiscal_year_id: number; fiscal_years: Option[]; fiscal_year: string; start_date: string; end_date: string;
  rows: { label: string; kind: string; account: string; start_cents: number; end_cents: number; change_cents: number }[];
  total: { start_cents: number; end_cents: number; change_cents: number }; result_cents: number;
}

export default function SimpleReportsPage() {
  const [params, setParams] = useUrlParams({ fiscal_year_id: "", tab: "result", year: String(new Date().getFullYear()) });
  const agri = useCurrentSession().instance?.chart === "agri";
  const query = params.fiscal_year_id ? `?fiscal_year_id=${params.fiscal_year_id}` : "";
  const statement = useQuery({ queryKey: ["simple-reports", "result", query], placeholderData: (p) => p,
    queryFn: () => api.get<Statement>(`/api/v1/simple/reports/income-statement${query}`) });
  const treasury = useQuery({ queryKey: ["simple-reports", "treasury", query], placeholderData: (p) => p,
    queryFn: () => api.get<Treasury>(`/api/v1/simple/reports/treasury${query}`) });
  const data = statement.data;
  if (!data || !treasury.data) return <Center h={300}><Loader /></Center>;
  const t = treasury.data;
  return (
    <>
      <PageHeader title="États" description={`Exercice ${data.fiscal_year}`}
        actions={<Button variant="default" leftSection={<Printer size={16} />} onClick={() => window.print()}>Imprimer</Button>} />
      <FilterBar>
        {agri && (params.tab === "book" || params.tab === "micro")
          ? <YearSelect value={params.year} onChange={(year) => setParams({ ...params, year })} />
          : <Select aria-label="Exercice" w={150} allowDeselect={false} data={data.fiscal_years}
            value={params.fiscal_year_id || String(data.fiscal_year_id)} onChange={(v) => setParams({ ...params, fiscal_year_id: v ?? "" })} />}
      </FilterBar>
      <Tabs value={params.tab} onChange={(v) => setParams({ ...params, tab: v ?? "result" })}>
        <Tabs.List mb="md"><Tabs.Tab value="result">Compte de résultat</Tabs.Tab><Tabs.Tab value="treasury">Situation de trésorerie</Tabs.Tab>
          {agri && <><Tabs.Tab value="book">Livre des recettes</Tabs.Tab><Tabs.Tab value="micro">Micro-BA</Tabs.Tab></>}</Tabs.List>
        {agri && <Tabs.Panel value="book">{params.tab === "book" && <ReceiptsBook year={params.year} />}</Tabs.Panel>}
        {agri && <Tabs.Panel value="micro">{params.tab === "micro" && <MicroBaSummary year={params.year} />}</Tabs.Panel>}
        <Tabs.Panel value="result">
          <Paper p={0}>
            <Table verticalSpacing={5}>
              <Table.Thead bg="var(--lv-sauge)"><Table.Tr><Table.Th />
                <Table.Th ta="right">{data.fiscal_year}</Table.Th><Table.Th ta="right">{data.previous_year ?? "N-1"}</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>
                {(["income", "expense"] as const).map((kind) => [
                  <Table.Tr key={`${kind}-h`}><Table.Td colSpan={3}><Text fw={700} size="sm">{kind === "income" ? "Recettes" : "Dépenses"}</Text></Table.Td></Table.Tr>,
                  ...data.rows.filter((r) => r.kind === kind).map((r) => (
                    <Table.Tr key={`${kind}-${r.label}`}><Table.Td><Text size="sm">{r.label}</Text></Table.Td>
                      <Table.Td ta="right"><MoneyText cents={r.amount_cents} size="sm" /></Table.Td>
                      <Table.Td ta="right"><MoneyText cents={r.previous_cents} size="sm" c="dimmed" /></Table.Td></Table.Tr>
                  )),
                  <Table.Tr key={`${kind}-t`}><Table.Td><Text size="sm" fw={600}>Total {kind === "income" ? "recettes" : "dépenses"}</Text></Table.Td>
                    <Table.Td ta="right"><MoneyText cents={data.totals[kind].amount_cents} fw={600} size="sm" /></Table.Td>
                    <Table.Td ta="right"><MoneyText cents={data.totals[kind].previous_cents} size="sm" c="dimmed" /></Table.Td></Table.Tr>,
                ])}
                <Table.Tr><Table.Td><Text fw={700}>{data.result.amount_cents >= 0 ? "Excédent" : "Déficit"}</Text></Table.Td>
                  <Table.Td ta="right"><MoneyText cents={data.result.amount_cents} fw={700} anomaly={data.result.amount_cents < 0} /></Table.Td>
                  <Table.Td ta="right"><MoneyText cents={data.result.previous_cents} c="dimmed" /></Table.Td></Table.Tr>
              </Table.Tbody>
            </Table>
          </Paper>
        </Tabs.Panel>
        <Tabs.Panel value="treasury">
          <Paper p={0} mb="md">
            <Table verticalSpacing={5}>
              <Table.Thead bg="var(--lv-sauge)"><Table.Tr><Table.Th>Compte</Table.Th><Table.Th ta="right">Au {formatDate(t.start_date)}</Table.Th>
                <Table.Th ta="right">Au {formatDate(t.end_date)}</Table.Th><Table.Th ta="right">Variation</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>
                {t.rows.map((r) => (
                  <Table.Tr key={r.account + r.label}><Table.Td><Text size="sm">{r.label}{r.kind === "cash" && " (caisse)"}</Text></Table.Td>
                    <Table.Td ta="right"><MoneyText cents={r.start_cents} size="sm" /></Table.Td>
                    <Table.Td ta="right"><MoneyText cents={r.end_cents} size="sm" /></Table.Td>
                    <Table.Td ta="right"><MoneyText cents={r.change_cents} plus size="sm" /></Table.Td></Table.Tr>
                ))}
                <Table.Tr><Table.Td><Text fw={700} size="sm">Trésorerie totale</Text></Table.Td>
                  <Table.Td ta="right"><MoneyText cents={t.total.start_cents} fw={700} size="sm" /></Table.Td>
                  <Table.Td ta="right"><MoneyText cents={t.total.end_cents} fw={700} size="sm" /></Table.Td>
                  <Table.Td ta="right"><MoneyText cents={t.total.change_cents} plus fw={700} size="sm" /></Table.Td></Table.Tr>
              </Table.Tbody>
            </Table>
          </Paper>
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <Paper p="md"><Text size="sm" c="dimmed">Résultat de l'exercice</Text><MoneyText cents={t.result_cents} fw={600} /></Paper>
            <Paper p="md"><Text size="sm" c="dimmed">Écart trésorerie − résultat</Text><MoneyText cents={t.total.change_cents - t.result_cents} fw={600} />
              <Text size="xs" c="dimmed">Mouvements sans effet sur le résultat (emprunt, caution, avance…).</Text></Paper>
          </SimpleGrid>
        </Tabs.Panel>
      </Tabs>
    </>
  );
}
