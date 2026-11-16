// Compta › Activités (lot AG8.a, claudedocs/design_analytique_agricole.md § 3, AGD25) : ateliers et activités
// (production Lexicon, nature, unité, dates théoriques du cycle qui déterminent la campagne), mesures par campagne
// (surface, effectif) servant aux clés de répartition et aux ratios.
import { useState } from "react";
import { Alert, Badge, Button, Center, Group, Loader, Paper, Select, Table, Text, TextInput, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan, useIntegration } from "../../api/session";
import { AppLink } from "../../app/navigation";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { PageHeader } from "../../components/PageHeader";
import { KeysPanel } from "./KeysPanel";

type Option = { value: string; label: string };
export interface ActivityRow {
  id: number; workshop_id: number; name: string; lexicon_reference: string | null; lexicon_name: string | null;
  nature: string; nature_label: string; cycle: string; unit: string; unit_label: string; cycle_start: string; cycle_stop: string;
  year_offset: number; isacompta_code: string | null; archived: boolean;
  distribution_key_id?: number | null; distribution_key?: string | null;
  campaign?: { year: number; start: string; stop: string; measure: string | null; production_id: number | null };
}
export interface WorkshopRow { id: number; name: string; family: string; family_label: string; isacompta_code: string | null;
  position: number; archived: boolean; activities: ActivityRow[] }
export interface ActivitiesView { campaign: number | null; workshops: WorkshopRow[]; campaigns: number[];
  totals: { unit: string; unit_label: string; measure: string }[] }
interface Meta { families: Option[]; natures: Option[]; cycles: Option[]; units: Option[];
  lexicon: { version: string; licence: string; provider: string; url: string } }
interface LexiconProduction { reference: string; name: string; family: string; unit: string; start: string; stop: string }

const day = (iso: string) => new Date(iso).toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
const fr = (m: string | null) => (m === null ? "" : m.replace(".", ","));

function MeasureInput({ activity, year, editable, onSave }: { activity: ActivityRow; year: number; editable: boolean;
  onSave: (value: string) => void }) {
  const [value, setValue] = useState(fr(activity.campaign?.measure ?? null));
  return (
    <TextInput size="xs" w={110} aria-label={`Mesure ${activity.name} ${year}`} value={value} disabled={!editable}
      rightSection={<Text size="xs" c="dimmed">{activity.unit_label}</Text>} rightSectionWidth={44}
      onChange={(e) => setValue(e.currentTarget.value)}
      onBlur={() => { if (value !== fr(activity.campaign?.measure ?? null)) onSave(value); }} />
  );
}

function ActivityForm({ workshop, meta, onDone }: { workshop: WorkshopRow; meta: Meta; onDone: () => void }) {
  const [draft, setDraft] = useState<{ name: string; lexicon: string | null; nature: string }>({ name: "", lexicon: null, nature: "main" });
  const [error, setError] = useState<string | null>(null);
  const { data } = useQuery({ queryKey: ["lexicon-productions", workshop.family],
    queryFn: () => api.get<{ items: LexiconProduction[] }>(`/api/v1/lexicon/productions?family=${workshop.family}`) });
  const create = useAction((b: object) => api.post<{ notices: Notice[] }>("/api/v1/activities", b), { invalidate: [["activities"]] });
  return (
    <Group align="end" gap="xs" mt="xs">
      <Select label="Production Lexicon" w={260} searchable clearable placeholder="facultative" value={draft.lexicon}
        data={(data?.items ?? []).map((p) => ({ value: p.reference, label: `${p.name} (${p.start.split("-").reverse().join("/")} → ${p.stop.split("-").reverse().join("/")})` }))}
        onChange={(x) => setDraft({ ...draft, lexicon: x, name: draft.name || (data?.items.find((p) => p.reference === x)?.name ?? "") })} />
      <TextInput label="Activité" w={200} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.currentTarget.value })} />
      <Select label="Nature" w={220} data={meta.natures} value={draft.nature} allowDeselect={false} onChange={(x) => setDraft({ ...draft, nature: x ?? "main" })} />
      <Button variant="light" loading={create.isPending} disabled={!draft.name && !draft.lexicon}
        onClick={() => { setError(null); create.mutateAsync({ workshop_id: workshop.id, name: draft.name, lexicon_reference: draft.lexicon, nature: draft.nature })
          .then(() => { setDraft({ name: "", lexicon: null, nature: "main" }); onDone(); }, (e) => setError(e instanceof ApiError ? e.message : "Création impossible.")); }}>
        Ajouter l'activité</Button>
      {error && <Text c="brique" size="sm">{error}</Text>}
    </Group>
  );
}

export default function ActivitiesPage() {
  const can = useCan();
  const ekylibre = useIntegration("ekylibre");
  const [params, setParams] = useUrlParams({ campaign: "" });
  const year = Number(params.campaign) || new Date().getFullYear();
  const { data, error } = useQuery({ queryKey: ["activities", year],
    queryFn: () => api.get<{ item: ActivitiesView; meta: Meta }>(`/api/v1/workshops?campaign=${year}`) });
  const [workshopDraft, setWorkshopDraft] = useState<{ name: string; family: string | null }>({ name: "", family: null });
  const [adding, setAdding] = useState<number | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const opts = { invalidate: [["activities"]] };
  const createWorkshop = useAction((b: object) => api.post<{ notices: Notice[] }>("/api/v1/workshops", b), opts);
  const removeWorkshop = useAction((id: number) => api.delete<{ notices: Notice[] }>(`/api/v1/workshops/${id}`), opts);
  const patchActivity = useAction(({ id, ...b }: { id: number; [key: string]: unknown }) => api.patch<{ notices: Notice[] }>(`/api/v1/activities/${id}`, b), opts);
  const measure = useAction(({ id, value }: { id: number; value: string }) => api.put<{ notices: Notice[] }>(`/api/v1/activities/${id}/campaigns/${year}`, { measure: value }), opts);
  const copy = useAction(() => api.post<{ notices: Notice[] }>(`/api/v1/campaigns/${year}/copy-measures`, {}), opts);
  const { data: keys } = useQuery({ queryKey: ["activities", "keys"], queryFn: () => api.get<{ items: { id: number; name: string }[] }>("/api/v1/analytic-keys") });
  const keyOptions = (keys?.items ?? []).map((k) => ({ value: String(k.id), label: k.name }));
  if (error) return <Alert color="paille">{error instanceof ApiError ? error.message : "Indisponible."}</Alert>;
  if (!data) return <Center h={300}><Loader /></Center>;
  const v = data.item;
  const run = (x: Promise<unknown>, after?: () => void) => { setFormError(null); x.then(after, (e) => setFormError(e instanceof ApiError ? e.message : "Action impossible.")); };
  const years = Array.from(new Set([...v.campaigns, year, new Date().getFullYear(), new Date().getFullYear() + 1])).sort((a, b) => b - a);
  return (
    <>
      <PageHeader title="Activités" description="Ateliers et activités de l'exploitation, et leurs surfaces ou effectifs par campagne : base de la ventilation analytique et des marges."
        actions={ekylibre && <Button variant="default" component={AppLink} href="/activities/ekylibre">Depuis Ekylibre</Button>} />
      <FilterBar>
        <Select aria-label="Campagne" w={170} allowDeselect={false} value={String(year)} data={years.map((y) => ({ value: String(y), label: `Campagne ${y}` }))}
          onChange={(x) => setParams({ campaign: x ?? "" })} />
        {v.totals.map((t) => <Badge key={t.unit} variant="light">{fr(t.measure)} {t.unit_label}</Badge>)}
        {can.write && <Button size="xs" variant="default" onClick={() => run(copy.mutateAsync(undefined))}>Reprendre les mesures de {year - 1}</Button>}
      </FilterBar>
      {formError && <Alert color="brique" mb="sm">{formError}</Alert>}
      {v.workshops.length === 0 && <Text c="dimmed" mb="md">Aucun atelier. Créez par exemple « Grandes cultures » ou « Vaches laitières ».</Text>}
      {v.workshops.map((w) => (
        <Paper key={w.id} withBorder p="md" mb="md">
          <Group justify="space-between">
            <Group gap="xs"><Title order={4}>{w.name}</Title><Badge variant="light" color="gray">{w.family_label}</Badge>
              {w.isacompta_code && <Text size="xs" c="dimmed">code {w.isacompta_code}</Text>}</Group>
            {can.write && w.activities.length === 0 && <Button size="compact-xs" variant="subtle" color="brique" onClick={() => run(removeWorkshop.mutateAsync(w.id))}>Supprimer l'atelier</Button>}
          </Group>
          {w.activities.length > 0 && (
            <Table mt="xs">
              <Table.Thead><Table.Tr><Table.Th>Activité</Table.Th><Table.Th>Nature</Table.Th><Table.Th>Cycle de la campagne {year}</Table.Th>
                <Table.Th>Mesure</Table.Th><Table.Th /></Table.Tr></Table.Thead>
              <Table.Tbody>
                {w.activities.map((a) => (
                  <Table.Tr key={a.id}>
                    <Table.Td><Text size="sm">{a.name}</Text>{a.lexicon_name && <Text size="xs" c="dimmed">Lexicon : {a.lexicon_name}</Text>}</Table.Td>
                    <Table.Td><Text size="sm">{a.nature_label}</Text>
                      {a.nature === "auxiliary" && (
                        <Select aria-label={`Clé de répartition de ${a.name}`} size="xs" w={190} placeholder="Clé de répartition" clearable
                          disabled={!can.write} data={keyOptions} value={a.distribution_key_id ? String(a.distribution_key_id) : null}
                          onChange={(x) => run(patchActivity.mutateAsync({ id: a.id, distribution_key_id: x ? Number(x) : null }))} />)}</Table.Td>
                    <Table.Td><Text size="sm">{a.campaign ? `${day(a.campaign.start)} → ${day(a.campaign.stop)}` : ""}</Text></Table.Td>
                    <Table.Td><MeasureInput key={`${a.id}-${year}-${a.campaign?.measure}`} activity={a} year={year} editable={can.write}
                      onSave={(value) => run(measure.mutateAsync({ id: a.id, value }))} /></Table.Td>
                    <Table.Td>{can.write && <Button size="compact-xs" variant="subtle" onClick={() => run(patchActivity.mutateAsync({ id: a.id, archived: true }))}>Archiver</Button>}</Table.Td>
                  </Table.Tr>))}
              </Table.Tbody>
            </Table>)}
          {can.write && (adding === w.id
            ? <ActivityForm workshop={w} meta={data.meta} onDone={() => setAdding(null)} />
            : <Button size="compact-sm" variant="subtle" mt="xs" onClick={() => setAdding(w.id)}>+ Activité</Button>)}
        </Paper>))}
      {can.write && (
        <Group align="end" gap="xs" mb="md">
          <TextInput label="Nouvel atelier" w={240} value={workshopDraft.name} onChange={(e) => setWorkshopDraft({ ...workshopDraft, name: e.currentTarget.value })} />
          <Select label="Famille" w={220} data={data.meta.families} value={workshopDraft.family} onChange={(x) => setWorkshopDraft({ ...workshopDraft, family: x })} />
          <Button variant="light" disabled={!workshopDraft.name || !workshopDraft.family} loading={createWorkshop.isPending}
            onClick={() => run(createWorkshop.mutateAsync({ name: workshopDraft.name, family: workshopDraft.family }), () => setWorkshopDraft({ name: "", family: null }))}>Créer l'atelier</Button>
        </Group>)}
      <KeysPanel editable={can.write} />
      <Text size="xs" c="dimmed">Productions et dates théoriques de cycle : Lexicon ({data.meta.lexicon.provider}, jeu productions {data.meta.lexicon.version}, licence {data.meta.lexicon.licence}).
        La campagne d'une dépense ou d'une recette est l'année de fin du cycle qui la contient.</Text>
    </>
  );
}
