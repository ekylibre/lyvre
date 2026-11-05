// Activités › clés de répartition et règles de compte (lot AG8.b, claudedocs/design_analytique_agricole.md §§ 4 et 5).
import { useState } from "react";
import { Alert, Badge, Button, Group, MultiSelect, Paper, Select, Table, Text, TextInput, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";

type Option = { value: string; label: string; group?: string };
export interface AnalyticKeyRow { id: number; name: string; basis: string; basis_label: string; warnings: string[];
  members: { activity_id: number; activity: string; workshop: string; share_bp: number | null }[] }
interface RuleRow { id: number; account_prefix: string; target: { kind: string; id: number; label: string } }

export function KeysPanel({ editable }: { editable: boolean }) {
  const { data } = useQuery({ queryKey: ["activities", "keys"], queryFn: () => api.get<{ items: AnalyticKeyRow[]; meta: { bases: Option[]; targets: Option[] } }>("/api/v1/analytic-keys") });
  const { data: rules } = useQuery({ queryKey: ["activities", "rules"], queryFn: () => api.get<{ items: RuleRow[] }>("/api/v1/analytic-rules") });
  const [draft, setDraft] = useState<{ name: string; basis: string; members: string[] }>({ name: "", basis: "surface", members: [] });
  const [error, setError] = useState<string | null>(null);
  const opts = { invalidate: [["activities"], ["analytic"]] };
  const create = useAction((b: object) => api.post<{ notices: Notice[] }>("/api/v1/analytic-keys", b), opts);
  const remove = useAction((id: number) => api.delete<{ notices: Notice[] }>(`/api/v1/analytic-keys/${id}`), opts);
  const removeRule = useAction((id: number) => api.delete<{ notices: Notice[] }>(`/api/v1/analytic-rules/${id}`), opts);
  if (!data) return null;
  const activities = data.meta.targets.filter((t) => t.value.startsWith("activity:"));
  const run = (x: Promise<unknown>, after?: () => void) => { setError(null); x.then(after, (e) => setError(e instanceof ApiError ? e.message : "Action impossible.")); };
  return (
    <Paper withBorder p="md" mb="md">
      <Title order={4} mb="xs">Clés de répartition</Title>
      {data.items.length > 0 && (
        <Table>
          <Table.Tbody>
            {data.items.map((k) => (
              <Table.Tr key={k.id}>
                <Table.Td><Text size="sm" fw={500}>{k.name}</Text><Text size="xs" c="dimmed">{k.basis_label}</Text></Table.Td>
                <Table.Td><Text size="sm">{k.members.map((m) => `${m.activity}${m.share_bp !== null ? ` ${(m.share_bp / 100).toLocaleString("fr-FR")} %` : ""}`).join(", ")}</Text>
                  {k.warnings.map((w) => <Badge key={w} size="xs" color="paille" mr={4}>{w}</Badge>)}</Table.Td>
                <Table.Td>{editable && <Button size="compact-xs" variant="subtle" color="brique" onClick={() => run(remove.mutateAsync(k.id))}>Supprimer</Button>}</Table.Td>
              </Table.Tr>))}
          </Table.Tbody>
        </Table>)}
      {editable && (
        <Group align="end" gap="xs" mt="xs">
          <TextInput label="Nouvelle clé" w={200} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.currentTarget.value })} />
          <Select label="Base" w={220} data={data.meta.bases.filter((b) => b.value !== "percentage")} value={draft.basis} allowDeselect={false}
            onChange={(x) => setDraft({ ...draft, basis: x ?? "surface" })} />
          <MultiSelect label="Activités" w={320} searchable data={activities.map((a) => ({ value: a.value, label: `${a.group} › ${a.label}` }))}
            value={draft.members} onChange={(x) => setDraft({ ...draft, members: x })} />
          <Button variant="light" disabled={!draft.name || !draft.members.length} loading={create.isPending}
            onClick={() => run(create.mutateAsync({ name: draft.name, basis: draft.basis, members: draft.members.map((m) => ({ activity_id: Number(m.split(":")[1]) })) }),
              () => setDraft({ name: "", basis: "surface", members: [] }))}>Créer la clé</Button>
        </Group>)}
      <Text size="xs" c="dimmed" mt={4}>Surface ou effectif : mesures des activités sur la campagne de chaque ligne. Clés en pourcentages : par l'API pour l'instant.</Text>
      <Title order={5} mt="md" mb="xs">Règles de compte</Title>
      {rules?.items.length ? rules.items.map((r) => (
        <Group key={r.id} gap="xs"><Text size="sm">{r.account_prefix} → {r.target.label}</Text>
          {editable && <Button size="compact-xs" variant="subtle" color="brique" onClick={() => run(removeRule.mutateAsync(r.id))}>Supprimer</Button>}</Group>))
        : <Text size="sm" c="dimmed">Aucune : créez-les depuis la ventilation analytique.</Text>}
      {error && <Alert color="brique" mt="xs">{error}</Alert>}
    </Paper>
  );
}
