// Résultat fiscal › aide à la liasse 2139 / 2143 (lot AG6.f, claudedocs/design_fiscalite_ba.md § 8) : cases et
// montants à recopier, par tableau, avec l'origine de chaque montant ; contrôles d'équilibre ; exports XLSX et PDF.
import { Accordion, Alert, Badge, Button, Group, Paper, Table, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { MoneyText } from "../../components/Money";

type Row = { case: string; label: string; kind: string; amount_cents: number | null; detail: boolean; note: string | null; unit: string | null;
  accounts: string[] | null; exclude: string[] | null };
export interface LiasseView {
  form: string | null; reason?: string; millesime?: number; title?: string; reliability?: string; not_covered?: string[]; warnings?: string[];
  tables: { code: string; title: string; rows: Row[]; checks: { label: string; ok: boolean; difference_cents: number }[] }[];
}

const origin = (r: Row) => (r.kind === "accounts" ? `${(r.accounts ?? []).join(", ")}${r.exclude?.length ? ` (sauf ${r.exclude.join(", ")})` : ""}`
  : r.kind === "tax" ? "résultat fiscal" : r.kind === "total" ? "total" : "à saisir");

export function LiassePanel({ fyId }: { fyId: number }) {
  const { data } = useQuery({ queryKey: ["tax-result", fyId, "liasse"], retry: false,
    queryFn: () => api.get<{ item: LiasseView }>(`/api/v1/fiscal-years/${fyId}/liasse`) });
  if (!data?.item) return null;
  const l = data.item;
  return (
    <Paper withBorder p="md" mt="lg">
      <Group justify="space-between" mb="xs">
        <Title order={4}>Aide à la liasse{l.form ? ` ${l.form} (millésime ${l.millesime})` : ""}</Title>
        {l.form && (
          <Group gap="xs">
            <Button size="xs" variant="default" component="a" href={`/fiscal-years/${fyId}/liasse.xlsx`}>XLSX</Button>
            <Button size="xs" variant="default" component="a" href={`/fiscal-years/${fyId}/liasse.pdf`} target="_blank">PDF</Button>
          </Group>)}
      </Group>
      {!l.form ? <Text size="sm">{l.reason}</Text> : (
        <>
          <Text size="xs" c="dimmed" mb="xs">Montants à recopier sur les formulaires officiels (pas de télétransmission). Correspondance
            comptes → cases proposée par Lyvre{l.reliability === "I" ? ", à valider par l'expert-comptable" : ""}.</Text>
          {(l.warnings ?? []).map((w) => <Alert key={w} color="paille" mb="xs">{w}</Alert>)}
          <Accordion multiple variant="separated">
            {l.tables.map((t) => (
              <Accordion.Item key={t.code} value={t.code}>
                <Accordion.Control>
                  <Group gap="xs">{t.code} — {t.title}
                    {t.checks.map((c) => <Badge key={c.label} size="sm" color={c.ok ? "mousse" : "brique"} variant="light" title={c.label}>{c.ok ? "équilibré" : "écart"}</Badge>)}
                  </Group>
                </Accordion.Control>
                <Accordion.Panel>
                  <Table>
                    <Table.Thead><Table.Tr><Table.Th>Case</Table.Th><Table.Th>Libellé</Table.Th><Table.Th ta="right">Montant</Table.Th><Table.Th>Origine</Table.Th></Table.Tr></Table.Thead>
                    <Table.Tbody>
                      {t.rows.map((r) => (
                        <Table.Tr key={r.case} fw={r.kind === "total" ? 600 : undefined}>
                          <Table.Td className="lv-num" fw={600}>{r.case}</Table.Td>
                          <Table.Td pl={r.detail ? "xl" : undefined}><Text size="sm" c={r.detail ? "dimmed" : undefined}>{r.label}</Text>
                            {r.note && <Text size="xs" c="dimmed">{r.note}</Text>}</Table.Td>
                          <Table.Td ta="right">{r.amount_cents === null ? <Text size="xs" c="dimmed">à saisir</Text> : <MoneyText cents={r.amount_cents} />}</Table.Td>
                          <Table.Td><Text size="xs" c="dimmed">{origin(r)}</Text></Table.Td>
                        </Table.Tr>))}
                    </Table.Tbody>
                  </Table>
                </Accordion.Panel>
              </Accordion.Item>))}
          </Accordion>
          {(l.not_covered ?? []).map((n) => <Text key={n} size="xs" c="dimmed" mt="xs">Non couvert : {n}</Text>)}
        </>)}
    </Paper>
  );
}
