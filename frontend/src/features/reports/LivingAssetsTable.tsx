// Annexe du bilan d'une exploitation agricole (art. 121-4 du titre 5, lot AG1.c) : biens vivants et en-cours de
// production, cycle long et cycle court, valeurs nettes à l'ouverture et à la clôture.
import { Paper, Table, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { MoneyText } from "../../components/Money";

interface Row { key: string; label: string; opening: number; closing: number }
interface Group { key: string; label: string; rows: Row[]; total: { opening: number; closing: number } }
interface Headcount { kind: string; label: string; opening: number; entries: number; exits: number; closing: number }
interface Response { item: { groups: Group[]; total: { opening: number; closing: number }; headcount?: Headcount[] } }

const AMOUNT = { width: 150, whiteSpace: "nowrap" } as const;
const ROMAN = ["I", "II"];

export function LivingAssetsTable({ fyId }: { fyId: string }) {
  const { data } = useQuery({
    queryKey: ["reports", "living-assets", fyId],
    queryFn: () => api.get<Response>(`/api/v1/reports/living-assets${fyId ? `?fy_id=${fyId}` : ""}`),
  });
  if (!data) return null;
  const { groups, total, headcount = [] } = data.item;
  return (
    <Paper p={0} mt="lg" style={{ overflowX: "auto" }}>
      <Title order={3} size="h5" p="sm">Annexe : biens vivants et en-cours de production</Title>
      <Table verticalSpacing={6} style={{ minWidth: 520 }}>
        <Table.Thead bg="var(--lv-sauge)">
          <Table.Tr><Table.Th>Nature</Table.Th><Table.Th ta="right" style={AMOUNT}>Valeur nette à l'ouverture</Table.Th>
            <Table.Th ta="right" style={AMOUNT}>Valeur nette à la clôture</Table.Th></Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {groups.map((g, i) => [
            <Table.Tr key={g.key} bg="var(--lv-surface-sunken)"><Table.Td colSpan={3}>
              <Text fw={700} size="sm">{g.label}</Text></Table.Td></Table.Tr>,
            ...g.rows.map((r) => (
              <Table.Tr key={`${g.key}-${r.key}`}>
                <Table.Td pl={24}><Text size="sm">{r.label}</Text></Table.Td>
                <Table.Td ta="right"><MoneyText cents={r.opening} /></Table.Td>
                <Table.Td ta="right"><MoneyText cents={r.closing} /></Table.Td>
              </Table.Tr>)),
            <Table.Tr key={`${g.key}-total`}>
              <Table.Td><Text size="sm" fw={600}>Total {ROMAN[i]}</Text></Table.Td>
              <Table.Td ta="right"><MoneyText cents={g.total.opening} fw={600} /></Table.Td>
              <Table.Td ta="right"><MoneyText cents={g.total.closing} fw={600} /></Table.Td>
            </Table.Tr>,
          ])}
          <Table.Tr bg="var(--lv-sauge)">
            <Table.Td><Text size="sm" fw={700}>TOTAL GÉNÉRAL (I + II)</Text></Table.Td>
            <Table.Td ta="right"><MoneyText cents={total.opening} fw={700} /></Table.Td>
            <Table.Td ta="right"><MoneyText cents={total.closing} fw={700} /></Table.Td>
          </Table.Tr>
        </Table.Tbody>
      </Table>
      {headcount.length > 0 && (
        <>
          <Title order={4} size="h6" p="sm">Effectifs des biens vivants immobilisés</Title>
          <Table verticalSpacing={6} style={{ minWidth: 520 }}>
            <Table.Thead bg="var(--lv-sauge)">
              <Table.Tr><Table.Th>Nature</Table.Th><Table.Th ta="right">Ouverture</Table.Th><Table.Th ta="right">Entrées</Table.Th>
                <Table.Th ta="right">Sorties</Table.Th><Table.Th ta="right">Clôture</Table.Th></Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {headcount.map((h) => (
                <Table.Tr key={h.kind}><Table.Td><Text size="sm">{h.label}</Text></Table.Td>
                  <Table.Td ta="right" className="lv-num">{h.opening}</Table.Td><Table.Td ta="right" className="lv-num">{h.entries}</Table.Td>
                  <Table.Td ta="right" className="lv-num">{h.exits}</Table.Td><Table.Td ta="right" className="lv-num">{h.closing}</Table.Td></Table.Tr>))}
            </Table.Tbody>
          </Table>
        </>)}
    </Paper>
  );
}
