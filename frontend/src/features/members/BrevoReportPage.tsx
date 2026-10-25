// Adhérents › Rapport Brevo (lot B3) : progression, compteurs, conflits à traiter, désinscrits restés
// désinscrits, adhérents sans e-mail, erreurs. Le rapport d'un aperçu propose de synchroniser.
import { useParams } from "react-router";
import { Alert, Anchor, Badge, Button, Center, Group, List, Loader, Paper, Progress, SimpleGrid, Stack, Table, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useCan } from "../../api/session";
import { PageHeader } from "../../components/PageHeader";
import { AppLink } from "../../app/navigation";
import { useStartBrevoSync } from "./BrevoMenu";

interface Person { entity_id: number | null; name: string; reason?: string }
interface Report {
  dry_run: boolean; created: number; linked: number; updated: number; unchanged: number; unlinked: number;
  conflicts: number; skipped: number; blacklisted: number; orphans: number; errors: string[];
  conflict_items: Person[]; blacklisted_items: Person[]; skipped_items: Person[];
}
interface Payload {
  job: { id: number; status: "running" | "done" | "failed"; message: string | null; progress_done: number; progress_total: number | null };
  result: Report | null; first_sync_pending: boolean;
}

const COUNTERS: [keyof Report, string, string][] = [
  ["created", "Créés", "nouveaux contacts"], ["linked", "Rattachés", "contacts déjà présents dans Brevo"],
  ["updated", "Mis à jour", "contacts déjà liés"], ["unchanged", "Inchangés", "aucun envoi"],
  ["unlinked", "Retirés de la liste", "adhérents sortis (contacts conservés)"],
];

function Tiers({ person }: { person: Person }) {
  return person.entity_id
    ? <Anchor component={AppLink} href={`/entities/${person.entity_id}`}>{person.name}</Anchor> : <Text span>{person.name}</Text>;
}

export default function BrevoReportPage() {
  const jobId = Number(useParams().job_id);
  const can = useCan();
  const start = useStartBrevoSync();
  const { data, isPending } = useQuery({
    queryKey: ["brevo", "sync", jobId], queryFn: () => api.get<Payload>(`/api/v1/brevo/sync/${jobId}`),
    refetchInterval: (q) => (q.state.data?.job.status === "running" ? 1500 : false),
  });
  if (isPending || !data) return <Center h={300}><Loader /></Center>;
  const { job, result: r } = data;

  return (
    <>
      <PageHeader title={r?.dry_run ? "Aperçu de la synchronisation Brevo" : "Synchronisation Brevo"}
        description={r?.dry_run ? "Rien n'a été écrit dans Brevo : voici ce que ferait la synchronisation." : undefined}
        actions={<Button variant="default" component={AppLink} href="/entities/members">Adhérents</Button>} />
      {job.status === "running" && (
        <Paper p="md" maw={640}><Stack gap="xs">
          <Text>{job.message ?? "En cours…"}</Text>
          <Progress value={job.progress_total ? (100 * job.progress_done) / job.progress_total : 5} animated />
        </Stack></Paper>
      )}
      {job.status === "failed" && <Alert color="brique" maw={760}>{job.message ?? "La synchronisation a échoué."}</Alert>}
      {r && (
        <Stack maw={960}>
          <SimpleGrid cols={{ base: 2, sm: 5 }}>
            {COUNTERS.map(([key, label, hint]) => (
              <Paper key={key} p="md">
                <Text size="sm" c="dimmed">{label}</Text>
                <Text className="lv-num" fz={26} fw={500}>{r[key] as number}</Text>
                <Text size="xs" c="dimmed">{hint}</Text>
              </Paper>
            ))}
          </SimpleGrid>
          {r.dry_run && can.write && job.status === "done" && (
            <Alert color="lichen" title="Aperçu terminé">
              <Group justify="space-between">
                <Text size="sm">Vérifiez les conflits ci-dessous, puis lancez la synchronisation : seuls les envois annoncés seront faits.</Text>
                <Button loading={start.isPending} onClick={() => start.run(false)}>Synchroniser</Button>
              </Group>
            </Alert>
          )}
          {r.errors.length > 0 && (
            <Alert color="brique" title={`${r.errors.length} erreur(s)`}>
              <List size="sm">{r.errors.map((e) => <List.Item key={e}>{e}</List.Item>)}</List>
            </Alert>
          )}
          {r.conflict_items.length > 0 && (
            <Stack gap="xs">
              <Title order={2} size="h4">Conflits à traiter ({r.conflicts})</Title>
              <Text size="sm" c="dimmed">Rien n'est fusionné ni modifié pour ces adhérents : corrigez l'e-mail dans Lyvre ou le contact dans Brevo.</Text>
              <Table>
                <Table.Tbody>
                  {r.conflict_items.map((c, i) => (
                    <Table.Tr key={i}><Table.Td><Tiers person={c} /></Table.Td><Table.Td><Text size="sm">{c.reason}</Text></Table.Td></Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Stack>
          )}
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <Paper p="md">
              <Group gap="xs" mb="xs"><Title order={3} size="h5">Désinscrits</Title><Badge variant="light">{r.blacklisted}</Badge></Group>
              <Text size="xs" c="dimmed" mb="xs">Mis à jour dans la liste, mais ils restent désinscrits : Lyvre ne les réinscrit jamais.</Text>
              <Stack gap={2}>{r.blacklisted_items.map((p, i) => <Tiers key={i} person={p} />)}</Stack>
            </Paper>
            <Paper p="md">
              <Group gap="xs" mb="xs"><Title order={3} size="h5">Sans e-mail</Title><Badge variant="light">{r.skipped}</Badge></Group>
              <Stack gap={2}>{r.skipped_items.map((p, i) => <Tiers key={i} person={p} />)}</Stack>
            </Paper>
          </SimpleGrid>
          {r.orphans > 0 && (
            <Text size="sm" c="dimmed">{r.orphans} contact(s) de la liste Brevo ne correspondent à aucun adhérent Lyvre : ils ne sont pas touchés.</Text>
          )}
        </Stack>
      )}
    </>
  );
}
