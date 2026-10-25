// Tiers › Revue Sirene (lot G5) : résultat de la comparaison des tiers avec Sirene. Tiers par tiers,
// champs à compléter (cochés) et champs différents (non cochés) ; « Appliquer la sélection » écrit en
// une fois, en sautant ce qui a changé depuis la comparaison. Tiers cessés, introuvables ou au
// numéro invalide : statut seul.
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router";
import {
  Alert, Anchor, Badge, Button, Center, Checkbox, Group, List, Loader, Paper, Progress, Stack, Table, Text, Title,
} from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { PageHeader } from "../../components/PageHeader";
import { AppLink, useGoTo } from "../../app/navigation";
import { formatNaf } from "../../lib/format";
import { TIERS_KEY } from "./types";

interface Change { field: string; label: string; current: string | null; proposed: string; computed: boolean; kind: "empty" | "different" }
interface Item {
  entity_id: number; name: string; state: "changes" | "up_to_date" | "ceased" | "not_found" | "invalid"; state_label: string;
  changes: Change[]; warnings: string[];
}
interface Review {
  job: { id: number; status: "running" | "done" | "failed"; message: string | null; progress_done: number; progress_total: number | null };
  result: { items: Item[]; total: number; compared: number; cancelled: boolean; applied_at?: string } | null;
  applied: boolean;
}
interface Skipped { entity_id: number | string; field: string | null; reason: string }

const KINDS: Record<string, string> = { individual: "Particulier", company: "Entreprise ou organisme" };
const show = (c: Change, value: string | null) =>
  !value ? "—" : c.field === "naf_code" ? formatNaf(value) : c.field === "person_kind" ? KINDS[value] ?? value : value;

export default function SireneReviewPage() {
  const jobId = Number(useParams().job_id);
  const can = useCan();
  const goTo = useGoTo();
  const client = useQueryClient();
  const key = ["sirene-review", jobId];
  const { data, isPending } = useQuery({
    queryKey: key, queryFn: () => api.get<Review>(`/api/v1/entities/sirene-refresh/${jobId}`),
    refetchInterval: (q) => (q.state.data?.job.status === "running" ? 1500 : false),
  });
  const items = useMemo(() => data?.result?.items ?? [], [data]);
  const toReview = items.filter((i) => i.state === "changes");
  const others = items.filter((i) => i.state === "ceased" || i.state === "not_found" || i.state === "invalid");
  const [checked, setChecked] = useState<Record<number, Set<string>>>({});
  useEffect(() => {
    setChecked(Object.fromEntries(items.filter((i) => i.state === "changes").map((i) =>
      [i.entity_id, new Set(i.changes.filter((c) => c.kind === "empty").map((c) => c.field))])));
  }, [items]);
  const [skipped, setSkipped] = useState<Skipped[] | null>(null);
  const cancel = useAction(() => api.post<{ notices: Notice[] }>(`/api/v1/entities/sirene-refresh/${jobId}/cancel`));
  const apply = useAction((changes: Record<number, string[]>) =>
    api.post<{ applied: number; skipped: Skipped[]; notices: Notice[] }>(`/api/v1/entities/sirene-refresh/${jobId}/apply`, { changes }),
  { invalidate: [TIERS_KEY, key] });

  if (isPending || !data) return <Center h={300}><Loader /></Center>;
  const { job, result } = data;
  const count = Object.values(checked).reduce((n, s) => n + s.size, 0);
  const toggle = (entityId: number, field: string) => setChecked((prev) => {
    const next = new Set(prev[entityId]);
    if (next.has(field)) next.delete(field); else next.add(field);
    return { ...prev, [entityId]: next };
  });
  const names = Object.fromEntries(items.map((i) => [i.entity_id, i.name]));

  return (
    <>
      <PageHeader title="Mise à jour des tiers depuis Sirene"
        description="Rien n'est modifié avant « Appliquer la sélection » : champs vides proposés cochés, champs différents à cocher."
        actions={<Button variant="default" component={AppLink} href="/entities/">Retour aux tiers</Button>} />
      {job.status === "running" && (
        <Paper p="md" maw={640}>
          <Stack gap="xs">
            <Text>{job.message ?? "Comparaison en cours…"}</Text>
            <Progress value={job.progress_total ? (100 * job.progress_done) / job.progress_total : 5} animated />
            {can.write && <Group><Button variant="default" size="compact-sm" loading={cancel.isPending}
              onClick={() => cancel.mutate(undefined)}>Arrêter</Button></Group>}
          </Stack>
        </Paper>
      )}
      {job.status === "failed" && <Alert color="brique">{job.message ?? "La comparaison a échoué."}</Alert>}
      {result && (
        <Stack maw={960}>
          {result.cancelled && <Alert color="paille">Comparaison arrêtée : {result.compared} tiers comparés sur {result.total}.</Alert>}
          {data.applied && <Alert color="lichen">Sélection appliquée le {new Date(result.applied_at!).toLocaleString("fr-FR")}.</Alert>}
          {skipped && skipped.length > 0 && (
            <Alert color="paille" title="Laissés tels quels">
              <List size="sm">{skipped.map((s, i) => (
                <List.Item key={i}>{names[Number(s.entity_id)] ?? `Tiers ${s.entity_id}`}{s.field && ` (${s.field})`} : {s.reason}</List.Item>
              ))}</List>
            </Alert>
          )}
          <Text c="dimmed">{toReview.length} tiers à revoir, {items.filter((i) => i.state === "up_to_date").length} déjà à jour,
            {" "}{others.length} sans proposition.</Text>
          {toReview.map((item) => (
            <Paper key={item.entity_id} p="md">
              <Group justify="space-between" mb="xs">
                <Anchor component={AppLink} href={`/entities/${item.entity_id}`} fw={600}>{item.name}</Anchor>
              </Group>
              {item.warnings.map((w) => <Text key={w} size="sm" c="dimmed">{w}</Text>)}
              <Table verticalSpacing={4}>
                <Table.Thead><Table.Tr><Table.Th w={32} /><Table.Th>Champ</Table.Th><Table.Th>Actuel</Table.Th><Table.Th>Sirene</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>
                  {item.changes.map((c) => (
                    <Table.Tr key={c.field}>
                      <Table.Td><Checkbox aria-label={`${item.name} : ${c.label}`} disabled={!can.write}
                        checked={!!checked[item.entity_id]?.has(c.field)} onChange={() => toggle(item.entity_id, c.field)} /></Table.Td>
                      <Table.Td>{c.label}{c.computed && <Badge size="xs" variant="light" color="ardoise" ml={6}>calculé</Badge>}</Table.Td>
                      <Table.Td c="dimmed">{show(c, c.current)}</Table.Td>
                      <Table.Td>{show(c, c.proposed)}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Paper>
          ))}
          {others.length > 0 && (
            <Stack gap="xs">
              <Title order={2} size="h4">Sans proposition</Title>
              <Table>
                <Table.Tbody>
                  {others.map((i) => (
                    <Table.Tr key={i.entity_id}>
                      <Table.Td><Anchor component={AppLink} href={`/entities/${i.entity_id}`}>{i.name}</Anchor></Table.Td>
                      <Table.Td><Badge variant="light" color={i.state === "ceased" ? "brique" : "gray"}>{i.state_label}</Badge></Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Stack>
          )}
          {can.write && job.status === "done" && !data.applied && toReview.length > 0 && (
            <Group>
              <Button disabled={!count} loading={apply.isPending} onClick={() => apply.mutate(
                Object.fromEntries(Object.entries(checked).filter(([, s]) => s.size).map(([id, s]) => [id, [...s]])),
                { onSuccess: (r) => { setSkipped(r.skipped); void client.invalidateQueries({ queryKey: key }); } })}>
                Appliquer la sélection ({count})</Button>
              <Button variant="default" onClick={() => goTo("/entities/")}>Abandonner</Button>
            </Group>
          )}
        </Stack>
      )}
    </>
  );
}
