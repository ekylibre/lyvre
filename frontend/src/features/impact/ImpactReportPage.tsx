// Indicateurs › Rapport « Visibilité & Impact » imprimable (Imprimer / PDF du navigateur).
import { Button, Center, Loader, Paper, SimpleGrid, Table, Text, Title } from "@mantine/core";
import { useCurrentSession } from "../../api/session";
import { PageHeader } from "../../components/PageHeader";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { useImpact } from "./ImpactPage";
import { delta } from "./types";

export default function ImpactReportPage() {
  const session = useCurrentSession();
  const { data, query } = useImpact();
  if (!data) return <Center h={300}><Loader /></Center>;
  return (
    <>
      <PageHeader title="Rapport « Visibilité & Impact »" description={`${session.instance?.label ?? ""} — ${data.period.label}`}
        actions={<>
          <Button variant="default" component={AppLink} href={`/impact/${query}`}>Tableau de bord</Button>
          <Button onClick={() => window.print()}>Imprimer / PDF</Button>
        </>} />
      <SimpleGrid cols={4} mb="lg">
        {data.highlights.map((h) => (
          <Paper key={h.key} p="sm" ta="center" withBorder>
            <Text fw={700} className="lv-num">{h.formatted}</Text><Text size="sm" c="dimmed">{h.label}</Text>
          </Paper>
        ))}
      </SimpleGrid>
      {data.sections.map((s) => (
        <div key={s.key} style={{ breakInside: "avoid" }}>
          <Title order={3} mb={4}>{s.label}</Title>
          <Table mb="lg">
            <Table.Thead><Table.Tr><Table.Th>Indicateur</Table.Th><Table.Th ta="right">Valeur</Table.Th>
              <Table.Th ta="right">Évolution</Table.Th><Table.Th>Source</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>{s.kpis.map((k) => (
              <Table.Tr key={k.key} c={k.available ? undefined : "dimmed"}>
                <Table.Td>{k.label}</Table.Td><Table.Td ta="right" fw={600} className="lv-num">{k.formatted}</Table.Td>
                <Table.Td ta="right" className="lv-num">{delta(k)?.text ?? "—"}</Table.Td><Table.Td><Text size="sm" c="dimmed">{k.source}</Text></Table.Td>
              </Table.Tr>
            ))}</Table.Tbody>
          </Table>
        </div>
      ))}
      <Text size="sm" c="dimmed" mt="md" pt="xs" style={{ borderTop: "1px solid var(--lv-line)" }}>
        <b>Sources et méthode.</b> Données internes (boutique POS, HelloAsso, bénévolat) calculées sur la période. Visibilité web :
        Google Analytics. Réseaux sans API (Vinted, groupe Facebook) : saisie manuelle. Impact environnemental : estimé à partir des
        articles remis en circulation et des facteurs ADEME Base Empreinte.
      </Text>
      <Text size="sm" c="dimmed" mt={4}>Fraîcheur des sources externes :{" "}
        {data.sources.map((s) => `${s.label} — ${s.fresh_at ? formatDate(s.fresh_at) : "non synchronisé"}`).join(" · ")}</Text>
    </>
  );
}
