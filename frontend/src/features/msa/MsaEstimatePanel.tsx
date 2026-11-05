// Cotisations MSA › estimation indicative (lot AG7.e, claudedocs/design_msa.md § 7) : barème NSA de la MSA appliqué à
// l'assiette retenue pour l'année de cotisation, ligne par ligne ; catégorie de risques ATEXA de l'exploitant.
import { Alert, Group, Select, Table, Text } from "@mantine/core";
import { MoneyText } from "../../components/Money";

export interface MsaEstimate {
  available: boolean; reason?: string; year?: number; base_cents?: number; warnings?: string[]; notes?: string[];
  lines?: { key: string; label: string; amount_cents: number; detail: string; group: string; deductible: boolean }[];
  totals?: { total_cents: number; contributions_cents: number; csg_crds_cents: number; non_deductible_cents: number; third_party_cents: number };
}

const CATEGORIES = ["A", "B", "C", "D", "E"].map((c) => ({ value: c, label: `Catégorie ${c}` }));

export function MsaEstimatePanel({ estimate: e, category, editable, onCategory }:
  { estimate: MsaEstimate; category: string | null; editable: boolean; onCategory: (value: string | null) => void }) {
  return (
    <>
      <Group justify="space-between" mt="md">
        <Text fw={600} size="sm">Estimation des cotisations {e.year ?? ""} (indicative)</Text>
        <Select aria-label="Catégorie de risques ATEXA" size="xs" w={170} placeholder="Catégorie ATEXA" data={CATEGORIES} clearable
          disabled={!editable} value={category} onChange={onCategory} />
      </Group>
      {!e.available ? <Text size="sm" c="dimmed">{e.reason}</Text> : (
        <>
          {e.warnings?.map((w) => <Alert key={w} color="paille" py={4} my={4}>{w}</Alert>)}
          <Table>
            <Table.Tbody>
              {e.lines?.map((l) => (
                <Table.Tr key={l.key}><Table.Td>{l.label}{!l.deductible && <Text span size="xs" c="dimmed"> · non déductible</Text>}</Table.Td>
                  <Table.Td><Text size="xs" c="dimmed">{l.detail}</Text></Table.Td>
                  <Table.Td ta="right"><MoneyText cents={l.amount_cents} /></Table.Td></Table.Tr>))}
              <Table.Tr><Table.Td fw={700}>Total estimé sur une assiette de <MoneyText cents={e.base_cents ?? 0} /></Table.Td><Table.Td />
                <Table.Td ta="right"><MoneyText cents={e.totals?.total_cents ?? 0} fw={700} /></Table.Td></Table.Tr>
            </Table.Tbody>
          </Table>
          {e.notes?.map((n) => <Text key={n} size="xs" c="dimmed">{n}</Text>)}
        </>)}
    </>
  );
}
