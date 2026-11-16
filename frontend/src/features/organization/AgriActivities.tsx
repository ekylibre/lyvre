// Structure › Activités et démarches (lot AG9a.a, claudedocs/design_echeancier_agricole.md § 3 E5) : profil des
// démarches d'une exploitation, qui décide des échéances applicables (PAC, MSA, employeur, phyto, irrigation, baux).
// Une réponse laissée vide vaut « non renseigné » : l'échéancier pose alors la question.
import { useEffect, useState } from "react";
import {
  ActionIcon, Alert, Badge, Button, Center, Fieldset, Group, Loader, MultiSelect, SegmentedControl, Select, SimpleGrid, Stack,
  Table, Text, TextInput, Tooltip,
} from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { ApiError, api } from "../../api/client";
import { showNotices, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";

type Option = { value: string; label: string };
export interface Lease { label: string; due: string; role: string }
export interface AgriProfile {
  [key: string]: boolean | string | string[] | Lease[] | undefined;
  productions?: string[]; msa_fund?: string; pacage?: string; leases?: Lease[];
}
interface Meta { booleans: Option[]; dates: Option[]; productions: Option[]; msa_funds: Option[]; lease_roles: Option[] }
export interface Hint { text: string; suggested: boolean; conflict: boolean }
type Response = { item: AgriProfile; meta: Meta; hints?: Record<string, Hint>; uses?: Record<string, string[]>; notices?: Notice[] };

export const AGRI_PROFILE_KEY = ["agri-profile"];
// Nombre d'échéances qui dépendent d'une réponse, avec leur liste au survol.
function Uses({ titles }: { titles?: string[] }) {
  if (!titles?.length) return null;
  return (
    <Tooltip multiline w={320} withArrow label={titles.join(" · ")}>
      <Badge variant="light" color="gray" size="sm" style={{ cursor: "help" }}>
        {titles.length} échéance{titles.length > 1 ? "s" : ""}
      </Badge>
    </Tooltip>);
}

// Indice tiré de la comptabilité : jamais une réponse, l'utilisateur confirme.
function HintText({ hint, conflict }: { hint?: Hint; conflict: boolean }) {
  if (!hint) return null;
  return <Text size="xs" c={conflict ? "brique" : "dimmed"}>{conflict ? "À vérifier, la comptabilité indique le contraire : " : "Indice dans la comptabilité : "}{hint.text}</Text>;
}

const TRI = [{ value: "yes", label: "Oui" }, { value: "no", label: "Non" }, { value: "", label: "Non renseigné" }];

export function AgriActivities() {
  const can = useCan();
  const readOnly = !can.instanceAdmin;
  const client = useQueryClient();
  const { data } = useQuery({ queryKey: AGRI_PROFILE_KEY, queryFn: () => api.get<Response>("/api/v1/agri-profile") });
  const [profile, setProfile] = useState<AgriProfile>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (data) setProfile(data.item); }, [data]);
  if (!data) return <Center h={200}><Loader /></Center>;
  const { meta } = data;
  const hints = data.hints ?? {};
  const uses = data.uses ?? {};
  const set = (key: string, value: AgriProfile[string]) => setProfile((p) => {
    const next = { ...p };
    if (value === undefined || value === "" || value === null) delete next[key]; else next[key] = value;
    return next;
  });
  const leases = profile.leases ?? [];
  const setLease = (index: number, patch: Partial<Lease>) =>
    set("leases", leases.map((l, i) => (i === index ? { ...l, ...patch } : l)));
  const save = async () => {
    setError(null);
    setSaving(true);
    try {
      const body = await api.put<Response>("/api/v1/agri-profile", profile);
      showNotices(body.notices);
      client.setQueryData(AGRI_PROFILE_KEY, body);
      void client.invalidateQueries({ queryKey: ["agenda"] });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Enregistrement impossible.");
    } finally {
      setSaving(false);
    }
  };
  return (
    <Stack maw={900}>
      <Text size="sm" c="dimmed">Ces réponses choisissent les échéances de votre échéancier. Laissez « non renseigné » si
        vous ne savez pas : l'échéance concernée vous posera la question.</Text>
      {error && <Alert color="brique" role="alert">{error}</Alert>}
      <Fieldset legend="Activités">
        <Stack>
          {meta.booleans.map((b) => {
            const hint = hints[b.value];
            const answer = profile[b.value];
            const unanswered = answer !== true && answer !== false;
            return (
              <Group key={b.value} justify="space-between" wrap="nowrap" align="flex-start">
                <Stack gap={2}>
                  <Group gap="xs"><Text size="sm">{b.label}</Text><Uses titles={uses[b.value]} /></Group>
                  <HintText hint={hint} conflict={!!hint && !unanswered && answer !== hint.suggested} />
                </Stack>
                <Group gap="xs" wrap="nowrap">
                  {hint && unanswered && !readOnly && (
                    <Button size="compact-xs" variant="subtle" onClick={() => set(b.value, hint.suggested)}>
                      Répondre {hint.suggested ? "oui" : "non"}</Button>)}
                  <SegmentedControl size="xs" data={TRI} disabled={readOnly} aria-label={b.label}
                    value={answer === true ? "yes" : answer === false ? "no" : ""}
                    onChange={(v) => set(b.value, v === "" ? undefined : v === "yes")} />
                </Group>
              </Group>);
          })}
          <MultiSelect label={<Group gap="xs" component="span">Productions <Uses titles={uses.productions} /></Group>}
            data={meta.productions} readOnly={readOnly} clearable
            value={profile.productions ?? []} onChange={(v) => set("productions", v)} />
          <HintText hint={hints.productions} conflict={!!hints.productions?.conflict} />
        </Stack>
      </Fieldset>
      <Fieldset legend="Organismes et dates">
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <Select label="Caisse MSA" data={meta.msa_funds} clearable readOnly={readOnly} value={profile.msa_fund ?? null}
            description="Les appels de cotisations suivent le calendrier de la caisse quand il est connu."
            onChange={(v) => set("msa_fund", v ?? undefined)} />
          <TextInput label="Numéro PACAGE" readOnly={readOnly} value={profile.pacage ?? ""}
            onChange={(e) => set("pacage", e.currentTarget.value)} />
          {meta.dates.map((d) => (
            <DateInput key={d.value} label={d.label} clearable valueFormat="DD/MM/YYYY" readOnly={readOnly}
              value={(profile[d.value] as string | undefined) ?? null} onChange={(v) => set(d.value, v ?? undefined)} />))}
        </SimpleGrid>
      </Fieldset>
      <Fieldset legend="Baux ruraux">
        <Stack>
          <Group gap="xs"><Text size="sm" c="dimmed">Échéance annuelle du fermage, par exemple 29/09 (Saint-Michel) ou 11/11 (Saint-Martin).</Text>
            <Uses titles={uses.leases} /></Group>
          <HintText hint={hints.leases} conflict={!!hints.leases?.conflict} />
          {leases.length > 0 && (
            <Table>
              <Table.Thead><Table.Tr><Table.Th>Bail</Table.Th><Table.Th>Échéance (MM-JJ)</Table.Th><Table.Th>Rôle</Table.Th><Table.Th /></Table.Tr></Table.Thead>
              <Table.Tbody>{leases.map((l, i) => (
                <Table.Tr key={i}>
                  <Table.Td><TextInput aria-label="Bail" readOnly={readOnly} value={l.label} onChange={(e) => setLease(i, { label: e.currentTarget.value })} /></Table.Td>
                  <Table.Td><TextInput aria-label="Échéance" w={100} readOnly={readOnly} placeholder="11-11" value={l.due}
                    onChange={(e) => setLease(i, { due: e.currentTarget.value })} /></Table.Td>
                  <Table.Td><Select aria-label="Rôle" data={meta.lease_roles} readOnly={readOnly} allowDeselect={false} value={l.role}
                    onChange={(v) => setLease(i, { role: v ?? "tenant" })} /></Table.Td>
                  <Table.Td>{!readOnly && <ActionIcon variant="subtle" color="brique" aria-label="Retirer le bail"
                    onClick={() => set("leases", leases.filter((_, j) => j !== i))}><Trash2 size={16} /></ActionIcon>}</Table.Td>
                </Table.Tr>))}
              </Table.Tbody>
            </Table>)}
          {!readOnly && (
            <Group>
              <Button variant="light" onClick={() => set("leases", [...leases, { label: "", due: "11-11", role: "tenant" }])}>Ajouter un bail</Button>
              {profile.leases === undefined && <Button variant="subtle" onClick={() => set("leases", [])}>Aucun bail rural</Button>}
            </Group>)}
        </Stack>
      </Fieldset>
      {!readOnly && <Group><Button onClick={() => void save()} loading={saving}>Enregistrer</Button></Group>}
    </Stack>
  );
}
