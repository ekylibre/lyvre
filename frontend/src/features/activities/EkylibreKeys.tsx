// Activités › Depuis Ekylibre › Clés (lot AG11.c) : coûts des interventions de l'exercice (intrants, main-d'œuvre,
// matériel, heures de matériel) ramenés en parts par activité ; calcul des clés « (Ekylibre) » et règles proposées.
import { useState } from "react";
import { Alert, Badge, Button, Checkbox, Group, Paper, Select, SimpleGrid, Stack, Table, Text, Title } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { Can } from "../../components/Can";

const KEY = ["ekylibre", "keys"] as const;

export interface EkylibreKeysData {
  fiscal_year: { id: number; label: string }; synced_at: string | null; interventions: number; without_target: number;
  fiscal_years?: { value: string; label: string }[];
  keys: { kind: string; name: string; unit: string; total: string; unassigned: string;
    members: { activity_id: number; activity: string; amount: string; share_bp: number }[] }[];
  rules: { prefix: string; label: string; key: string; key_id: number | null; existing: string | null }[];
}

const fr = (v: string) => Number(v).toLocaleString("fr-FR", { maximumFractionDigits: 2 });
const pct = (bp: number) => `${(bp / 100).toLocaleString("fr-FR", { maximumFractionDigits: 2 })} %`;

export function EkylibreKeysView({ data, onCompute, onRules, pending }: {
  data: EkylibreKeysData; onCompute: () => void; onRules: (prefixes: string[]) => void; pending?: boolean;
}) {
  const [chosen, setChosen] = useState<string[]>([]);
  const free = data.rules.filter((r) => !r.existing);
  return (
    <Stack>
      <Text size="sm">{data.interventions} intervention(s) réalisée(s) sur l'exercice {data.fiscal_year.label}
        {data.without_target ? `, dont ${data.without_target} sans culture visée` : ""}. Les coûts d'Ekylibre servent de poids :
        ils ne sont pas comptabilisés.</Text>
      <SimpleGrid cols={{ base: 1, md: 2 }}>
        {data.keys.map((k) => (
          <Paper key={k.kind} p="sm">
            <Group justify="space-between"><Text fw={600}>{k.name}</Text>
              <Text size="sm" className="lv-num">{fr(k.total)} {k.unit}</Text></Group>
            {k.members.length === 0 ? <Text size="sm" c="dimmed">Rien à répartir.</Text> : (
              <Table><Table.Tbody>{k.members.map((m) => (
                <Table.Tr key={m.activity_id}><Table.Td>{m.activity}</Table.Td>
                  <Table.Td ta="right" className="lv-num">{fr(m.amount)} {k.unit}</Table.Td>
                  <Table.Td ta="right" className="lv-num">{pct(m.share_bp)}</Table.Td></Table.Tr>))}</Table.Tbody></Table>)}
            {Number(k.unassigned) > 0 && <Text size="xs" c="dimmed">Non imputé (culture non rattachée ou sans cible) : {fr(k.unassigned)} {k.unit}</Text>}
          </Paper>
        ))}
      </SimpleGrid>
      <Can><Group justify="flex-end"><Button loading={pending} disabled={!data.interventions} onClick={onCompute}>
        Calculer les clés de l'exercice</Button></Group></Can>
      {data.rules.length > 0 && <Paper p="sm">
        <Title order={4} mb={4}>Règles proposées</Title>
        <Text size="sm" c="dimmed" mb="xs">Les lignes de ces comptes, non encore ventilées, suivront la clé. Une ligne déjà ventilée garde sa ventilation.</Text>
        <Checkbox.Group value={chosen} onChange={setChosen}>
          <Stack gap={4}>{data.rules.map((r) => (
            <Group key={r.prefix} gap="xs">
              <Checkbox value={r.prefix} disabled={!!r.existing || !r.key_id} label={`${r.prefix} — ${r.label} → ${r.key}`} />
              {r.existing && <Badge variant="light" color="gray">déjà : {r.existing}</Badge>}
              {!r.existing && !r.key_id && <Badge variant="light" color="paille">clé à calculer</Badge>}
            </Group>))}</Stack>
        </Checkbox.Group>
        <Can><Group justify="flex-end" mt="xs"><Button variant="default" disabled={!chosen.length || !free.length}
          onClick={() => { onRules(chosen); setChosen([]); }}>Créer les règles ({chosen.length})</Button></Group></Can>
      </Paper>}
    </Stack>
  );
}

export function EkylibreKeys() {
  const client = useQueryClient();
  const [fy, setFy] = useState<string | null>(null);
  const { data } = useQuery({ queryKey: [...KEY, fy],
    queryFn: () => api.get<EkylibreKeysData>(`/api/v1/ekylibre/keys${fy ? `?fiscal_year_id=${fy}` : ""}`) });
  const compute = useAction(() => api.post<EkylibreKeysData & { notices: Notice[] }>("/api/v1/ekylibre/keys",
    { fiscal_year_id: fy ? Number(fy) : undefined }));
  const rules = useAction((prefixes: string[]) => api.post<{ notices: Notice[] }>("/api/v1/ekylibre/rules", { prefixes }));
  const refresh = () => { void client.invalidateQueries({ queryKey: KEY }); void client.invalidateQueries({ queryKey: ["activities"] }); };
  if (!data) return null;
  return (
    <Paper p="md">
      <Group justify="space-between" mb="sm">
        <Title order={3}>Clés de répartition depuis les interventions</Title>
        <Select aria-label="Exercice" w={160} allowDeselect={false} data={data.fiscal_years ?? []}
          value={fy ?? String(data.fiscal_year.id)} onChange={setFy} />
      </Group>
      {!data.synced_at && <Alert color="paille" mb="sm">Ekylibre n'a pas encore été lu.</Alert>}
      <EkylibreKeysView data={data} pending={compute.isPending}
        onCompute={() => compute.mutate(undefined, { onSuccess: refresh })}
        onRules={(prefixes) => rules.mutate(prefixes, { onSuccess: refresh })} />
    </Paper>
  );
}
