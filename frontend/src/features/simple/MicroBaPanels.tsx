// Exploitation agricole au micro-BA (lot AG1.d) : livre des recettes (CGI art. 64 bis IV) et récapitulatif des
// recettes de N, N-1 et N-2 avec le bénéfice forfaitaire (déclaration 2042 C PRO).
import { useState } from "react";
import { Alert, Badge, Button, Checkbox, Group, Paper, Select, SimpleGrid, Table, Text } from "@mantine/core";
import { Download } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { MoneyInput, MoneyText } from "../../components/Money";
import { formatDate } from "../../lib/format";
import { RELIABILITY_COLORS } from "../organization/FiscalProfile";

interface BookItem { date: string; label: string; entity: string | null; category: string; excluded: boolean;
  amount_cents: number; grouped?: number }
interface Book {
  year: number; grouping_cents: number | null; items: BookItem[]; export_url: string;
  quarters: { quarter: number; retained_cents: number; excluded_cents: number }[];
  total: { retained_cents: number; excluded_cents: number; receipts_cents: number };
}
interface YearReceipts { year: number; receipts_cents: number | null; source: "entered" | "lyvre" | "missing"; note: string | null }
interface Summary {
  year: number; years: YearReceipts[]; average_cents: number | null; allowance_bp: number | null; minimum_cents: number | null;
  profit_cents: number | null; threshold_cents: number | null; warnings: string[];
  reliability: Record<"allowance" | "minimum" | "threshold", string | null>;
}

const thisYear = new Date().getFullYear();
const YEARS = Array.from({ length: 6 }, (_, i) => String(thisYear - i));

export function YearSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return <Select aria-label="Année civile" w={110} allowDeselect={false} data={YEARS} value={value} onChange={(v) => onChange(v ?? value)} />;
}

export function ReceiptsBook({ year }: { year: string }) {
  const [group, setGroup] = useState(true);
  const { data } = useQuery({ queryKey: ["micro-ba", "book", year, group],
    queryFn: () => api.get<Book>(`/api/v1/simple/reports/receipts-book?year=${year}&group_small=${group ? 1 : 0}`) });
  if (!data) return null;
  return (
    <>
      <Group mb="sm" justify="space-between">
        <Checkbox checked={group} onChange={(e) => setGroup(e.currentTarget.checked)}
          label={`Regrouper par jour les ventes au détail${data.grouping_cents ? ` d'au plus ${(data.grouping_cents / 100).toLocaleString("fr-FR")} €` : ""}`} />
        <Button variant="default" component="a" href={data.export_url} leftSection={<Download size={16} />}>Exporter en XLSX</Button>
      </Group>
      <Paper p={0} mb="md">
        <Table verticalSpacing={4} striped>
          <Table.Thead bg="var(--lv-sauge)"><Table.Tr><Table.Th>Date</Table.Th><Table.Th>Libellé</Table.Th><Table.Th>Client</Table.Th>
            <Table.Th>Catégorie</Table.Th><Table.Th ta="right">Montant</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {data.items.map((item, i) => (
              <Table.Tr key={i}>
                <Table.Td className="lv-num">{formatDate(item.date)}</Table.Td>
                <Table.Td><Text size="sm">{item.label}</Text></Table.Td>
                <Table.Td><Text size="sm">{item.entity ?? ""}</Text></Table.Td>
                <Table.Td><Text size="sm">{item.category}{item.excluded && <Badge ml={6} size="xs" color="paille">exclue du micro-BA</Badge>}</Text></Table.Td>
                <Table.Td ta="right"><MoneyText cents={item.amount_cents} size="sm" /></Table.Td>
              </Table.Tr>))}
          </Table.Tbody>
        </Table>
      </Paper>
      <SimpleGrid cols={{ base: 2, sm: 6 }}>
        {data.quarters.map((q) => (
          <Paper key={q.quarter} p="sm"><Text size="xs" c="dimmed">Trimestre {q.quarter}</Text><MoneyText cents={q.retained_cents} fw={600} /></Paper>))}
        <Paper p="sm"><Text size="xs" c="dimmed">Recettes retenues {data.year}</Text><MoneyText cents={data.total.retained_cents} fw={700} /></Paper>
        <Paper p="sm"><Text size="xs" c="dimmed">Exclues du micro-BA</Text><MoneyText cents={data.total.excluded_cents} fw={600} /></Paper>
      </SimpleGrid>
    </>
  );
}

function Carryover({ year, row }: { year: string; row: YearReceipts }) {
  const client = useQueryClient();
  const [value, setValue] = useState<number | null>(row.source === "entered" ? row.receipts_cents : null);
  const save = useAction((cents: number | null) => api.put<{ notices: Notice[] }>(
    `/api/v1/simple/reports/micro-ba/carryover?year=${year}`, { year: row.year, receipts_cents: cents }));
  return (
    <Group gap="xs" wrap="nowrap">
      <MoneyInput aria-label={`Recettes ${row.year}`} w={150} value={value} onChange={setValue} />
      <Button size="compact-sm" variant="light" loading={save.isPending}
        onClick={() => save.mutate(value, { onSuccess: () => client.invalidateQueries({ queryKey: ["micro-ba"] }) })}>
        Enregistrer</Button>
    </Group>
  );
}

const SOURCES = { entered: "saisie", lyvre: "Lyvre", missing: "inconnue" };

export function MicroBaSummary({ year }: { year: string }) {
  const can = useCan();
  const { data } = useQuery({ queryKey: ["micro-ba", "summary", year],
    queryFn: () => api.get<Summary>(`/api/v1/simple/reports/micro-ba?year=${year}`) });
  if (!data) return null;
  const badge = (key: keyof Summary["reliability"]) => data.reliability[key] && (
    <Badge ml={6} size="xs" color={RELIABILITY_COLORS[data.reliability[key]!] ?? "gray"}>{data.reliability[key]}</Badge>);
  return (
    <>
      {data.warnings.map((w) => <Alert key={w} color="paille" mb="sm">{w}</Alert>)}
      <Paper p={0} mb="md">
        <Table verticalSpacing={6}>
          <Table.Thead bg="var(--lv-sauge)"><Table.Tr><Table.Th>Année</Table.Th><Table.Th ta="right">Recettes retenues</Table.Th>
            <Table.Th>Origine</Table.Th>{can.write && <Table.Th>Années antérieures à Lyvre</Table.Th>}</Table.Tr></Table.Thead>
          <Table.Tbody>
            {data.years.map((row) => (
              <Table.Tr key={row.year}>
                <Table.Td className="lv-num">{row.year}</Table.Td>
                <Table.Td ta="right">{row.receipts_cents === null ? "—" : <MoneyText cents={row.receipts_cents} size="sm" />}</Table.Td>
                <Table.Td><Text size="sm" c="dimmed">{SOURCES[row.source]}</Text></Table.Td>
                {can.write && <Table.Td>{row.year !== data.year && <Carryover year={year} row={row} />}</Table.Td>}
              </Table.Tr>))}
          </Table.Tbody>
        </Table>
      </Paper>
      <SimpleGrid cols={{ base: 1, sm: 4 }}>
        <Paper p="md"><Text size="sm" c="dimmed">Moyenne triennale</Text>
          {data.average_cents === null ? "—" : <MoneyText cents={data.average_cents} fw={600} />}</Paper>
        <Paper p="md"><Text size="sm" c="dimmed">Abattement{badge("allowance")}</Text>
          <Text fw={600}>{data.allowance_bp === null ? "—" : `${data.allowance_bp / 100} %`}</Text></Paper>
        <Paper p="md"><Text size="sm" c="dimmed">Bénéfice forfaitaire{badge("minimum")}</Text>
          {data.profit_cents === null ? "—" : <MoneyText cents={data.profit_cents} fw={700} />}</Paper>
        <Paper p="md"><Text size="sm" c="dimmed">Seuil du micro-BA{badge("threshold")}</Text>
          {data.threshold_cents === null ? "—" : <MoneyText cents={data.threshold_cents} fw={600} />}</Paper>
      </SimpleGrid>
      <Text size="xs" c="dimmed" mt="sm">À reporter sur la 2042 C PRO : recettes de {data.year}, {data.year - 1} et {data.year - 2}.
        Plus-values et moins-values de cession se calculent à part.</Text>
    </>
  );
}
