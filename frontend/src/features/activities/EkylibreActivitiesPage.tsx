// Activités › Depuis Ekylibre (lot AG11.b) : activités lues dans Ekylibre (dernière lecture), rattachées à une
// activité Lyvre (identifiant, nom, production Lexicon) ou à créer ; surfaces des cultures par campagne, reportées
// comme mesures sauf une surface saisie dans Lyvre (écart signalé) ; contrôle avec la surface des parcelles.
import { useState } from "react";
import { Alert, Anchor, Badge, Button, Checkbox, Group, Paper, Select, Stack, Table, Text } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { Can } from "../../components/Can";
import { PageHeader } from "../../components/PageHeader";
import { formatDateTime } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { EkylibreKeys } from "./EkylibreKeys";

const KEY = ["ekylibre", "activities"] as const;
const HOW: Record<string, string> = { ekylibre: "déjà rattachée", name: "même nom", lexicon: "même production Lexicon" };
const STATES: Record<string, { label: string; color: string }> = {
  new: { label: "à reporter", color: "ardoise" }, same: { label: "à jour", color: "lichen" },
  update: { label: "à mettre à jour", color: "ardoise" }, conflict: { label: "saisie différente", color: "paille" },
};

export interface EkylibreActivityRow {
  ekylibre_id: number; name: string; productions: number;
  activity: { id: number; name: string; how: string; unit: string } | null;
  proposal: { name: string; lexicon_reference: string | null } | null;
  campaigns: { year: number; surface_ha: string; lyvre_ha: string | null; state: keyof typeof STATES }[];
}

interface Data { synced_at: string | null; items: EkylibreActivityRow[]; warnings: string[] }
type Choice = { checked: boolean; target: string };   // target : id d'activité Lyvre, ou "new"

/** Tableau de rattachement : une ligne par activité Ekylibre, cible choisie, surfaces par campagne. */
export function EkylibreActivitiesTable({ items, activities, onApply, pending }: {
  items: EkylibreActivityRow[]; activities: { value: string; label: string }[];
  onApply: (body: { ekylibre_id: number; activity_id?: number; create?: boolean }[]) => void; pending?: boolean;
}) {
  const [choices, setChoices] = useState<Record<number, Choice>>(() => Object.fromEntries(items.map((r) =>
    [r.ekylibre_id, { checked: true, target: r.activity ? String(r.activity.id) : "new" }])));
  const set = (id: number, patch: Partial<Choice>) => setChoices((c) => ({ ...c, [id]: { ...c[id], ...patch } }));
  const chosen = items.filter((r) => choices[r.ekylibre_id]?.checked);
  const apply = () => onApply(chosen.map((r) => {
    const target = choices[r.ekylibre_id].target;
    return target === "new" ? { ekylibre_id: r.ekylibre_id, create: true } : { ekylibre_id: r.ekylibre_id, activity_id: Number(target) };
  }));
  return (
    <Paper p={0}>
      <Table>
        <Table.Thead><Table.Tr><Table.Th /><Table.Th>Activité Ekylibre</Table.Th><Table.Th>Activité Lyvre</Table.Th>
          <Table.Th>Surfaces (ha) par campagne</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>
          {items.map((r) => (
            <Table.Tr key={r.ekylibre_id}>
              <Table.Td><Checkbox aria-label={`Retenir ${r.name}`} checked={choices[r.ekylibre_id]?.checked ?? false}
                onChange={(e) => set(r.ekylibre_id, { checked: e.currentTarget.checked })} /></Table.Td>
              <Table.Td>{r.name}<Text size="xs" c="dimmed">{r.productions} culture(s)</Text></Table.Td>
              <Table.Td miw={240}>
                <Select size="xs" aria-label={`Activité Lyvre pour ${r.name}`} allowDeselect={false}
                  data={[{ value: "new", label: `Créer « ${r.proposal?.name ?? r.name} »` }, ...activities]}
                  value={choices[r.ekylibre_id]?.target} onChange={(v) => set(r.ekylibre_id, { target: v ?? "new" })} />
                {r.activity && <Text size="xs" c="dimmed">{HOW[r.activity.how]}</Text>}
                {!r.activity && r.proposal?.lexicon_reference && <Text size="xs" c="dimmed">production Lexicon reconnue</Text>}
              </Table.Td>
              <Table.Td>
                <Group gap={6}>{r.campaigns.map((c) => (
                  <Badge key={c.year} variant="light" color={STATES[c.state].color} title={c.lyvre_ha ? `Lyvre : ${c.lyvre_ha} ha` : undefined}>
                    {c.year} : {c.surface_ha.replace(".", ",")} ha · {STATES[c.state].label}</Badge>))}</Group>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      <Can><Group justify="flex-end" p="sm">
        <Button disabled={!chosen.length} loading={pending} onClick={apply}>Rattacher et reporter les surfaces ({chosen.length})</Button>
      </Group></Can>
    </Paper>
  );
}

export default function EkylibreActivitiesPage() {
  const client = useQueryClient();
  const { data } = useQuery({ queryKey: KEY, queryFn: () => api.get<Data>("/api/v1/ekylibre/activities") });
  const listing = useQuery({ queryKey: ["activities", "options"],
    queryFn: () => api.get<{ item: { workshops: { activities: { id: number; name: string; archived: boolean }[] }[] } }>("/api/v1/workshops") });
  const save = useAction((items: unknown[]) => api.post<Data & { notices: Notice[] }>("/api/v1/ekylibre/activities", { items }));
  const activities = (listing.data?.item.workshops ?? []).flatMap((w) => w.activities).filter((a) => !a.archived)
    .map((a) => ({ value: String(a.id), label: a.name }));
  return (
    <>
      <PageHeader title="Activités depuis Ekylibre"
        description="Rattachez chaque activité d'Ekylibre à une activité de Lyvre (ou créez-la) : la surface de ses cultures est reportée sur chaque campagne. Une surface saisie dans Lyvre n'est jamais remplacée."
        actions={<Button variant="default" component={AppLink} href="/activities/">Activités</Button>} />
      {data && <Stack>
        <Text size="sm" c="dimmed">{data.synced_at ? `Dernière lecture d'Ekylibre : ${formatDateTime(data.synced_at)}.` : "Ekylibre n'a pas encore été lu."}{" "}
          <Anchor component={AppLink} href="/configuration/integrations/ekylibre" size="sm">Lire Ekylibre</Anchor></Text>
        {data.warnings.map((w) => <Alert key={w} color="paille">{w}</Alert>)}
        {data.items.length === 0 ? <Text c="dimmed">Aucune culture avec activité et surface dans la dernière lecture.</Text>
          : <EkylibreActivitiesTable key={data.synced_at ?? ""} items={data.items} activities={activities} pending={save.isPending}
            onApply={(items) => save.mutate(items, { onSuccess: (r) => {
              client.setQueryData(KEY, { synced_at: r.synced_at, items: r.items, warnings: r.warnings });
              void client.invalidateQueries({ queryKey: ["activities"] });
            } })} />}
        <EkylibreKeys />
      </Stack>}
    </>
  );
}
