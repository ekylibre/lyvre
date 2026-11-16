// Intégration Ekylibre (lot AG11.a) : connexion par mot de passe à usage unique (Lyvre ne garde que le jeton),
// révocation du jeton, lecture d'Ekylibre en tâche de fond vers un instantané local (cultures, interventions,
// matières), date et volume de chaque instantané.
import { useState } from "react";
import { Button, Group, Paper, PasswordInput, SimpleGrid, Stack, Table, Text, TextInput, Title } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { ConfirmButton } from "../../components/ConfirmButton";
import { JobStatus, type Job } from "../../components/JobStatus";
import { formatDateTime } from "../../lib/format";

const KEY = ["ekylibre", "state"] as const;

export interface EkylibreState {
  enabled: boolean; configured: boolean; url: string; email: string; job: Job | null;
  snapshots: Record<"productions" | "parcels" | "interventions" | "matters", { label: string; count: number | null; synced_at: string | null }>;
}

export function EkylibreConnection({ onChange }: { onChange?: () => void }) {
  const client = useQueryClient();
  const { data } = useQuery({ queryKey: KEY, queryFn: () => api.get<EkylibreState>("/api/v1/ekylibre") });
  const [form, setForm] = useState<{ url: string | null; email: string | null; password: string }>({ url: null, email: null, password: "" });
  const [job, setJob] = useState<Job | null>(null);
  const done = () => { void client.invalidateQueries({ queryKey: KEY }); onChange?.(); };
  const connect = useAction(() => api.post<EkylibreState & { notices: Notice[] }>("/api/v1/ekylibre/connect", {
    url: form.url ?? data?.url ?? "", email: form.email ?? data?.email ?? "", password: form.password }));
  const revoke = useAction(() => api.post<EkylibreState & { notices: Notice[] }>("/api/v1/ekylibre/revoke"));
  const sync = useAction(() => api.post<{ job: Job; notices?: Notice[] }>("/api/v1/ekylibre/sync"));
  if (!data) return null;
  const shown = job ?? data.job;
  return (
    <Paper p="md" mb="md">
      <Title order={3} mb="xs">Connexion et lecture</Title>
      <Stack gap="sm">
        <form onSubmit={(e) => { e.preventDefault(); connect.mutate(undefined, { onSuccess: () => { setForm({ url: null, email: null, password: "" }); done(); } }); }}>
          <SimpleGrid cols={{ base: 1, md: 3 }}>
            <TextInput label="Adresse de l'instance" placeholder="https://ferme.ekylibre.farm" required
              value={form.url ?? data.url} onChange={(e) => setForm({ ...form, url: e.currentTarget.value })} />
            <TextInput label="Email Ekylibre" required value={form.email ?? data.email}
              onChange={(e) => setForm({ ...form, email: e.currentTarget.value })} />
            <PasswordInput label="Mot de passe" required value={form.password} autoComplete="off"
              description="Sert une fois à obtenir le jeton ; il n'est pas conservé."
              onChange={(e) => setForm({ ...form, password: e.currentTarget.value })} />
          </SimpleGrid>
          <Group justify="flex-end" mt="sm">
            {data.configured && <ConfirmButton variant="default" title="Révoquer le jeton Ekylibre ?" confirmLabel="Révoquer"
              message="Le jeton est révoqué chez Ekylibre et effacé de Lyvre ; les données déjà lues restent." loading={revoke.isPending}
              onConfirm={() => revoke.mutate(undefined, { onSuccess: done })}>Révoquer le jeton</ConfirmButton>}
            <Button type="submit" loading={connect.isPending}>{data.configured ? "Se reconnecter" : "Se connecter"}</Button>
          </Group>
        </form>
        {data.configured && <Text size="sm" c="dimmed">Jeton de {data.email} sur {data.url}. Lyvre lit Ekylibre et n'y écrit jamais.</Text>}
        <Table>
          <Table.Thead><Table.Tr><Table.Th>Données lues</Table.Th><Table.Th ta="right">Nombre</Table.Th><Table.Th>Lecture</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>{Object.entries(data.snapshots).map(([kind, s]) => (
            <Table.Tr key={kind}><Table.Td>{s.label}</Table.Td><Table.Td ta="right" className="lv-num">{s.count ?? "—"}</Table.Td>
              <Table.Td className="lv-num">{s.synced_at ? formatDateTime(s.synced_at) : "jamais"}</Table.Td></Table.Tr>))}</Table.Tbody>
        </Table>
        {shown && <JobStatus key={shown.id} job={shown} onDone={done}
          titles={{ running: "Lecture d'Ekylibre en cours…", done: "Lecture d'Ekylibre terminée", failed: "La lecture d'Ekylibre a échoué" }} />}
        <Group justify="flex-end">
          <Button variant="default" disabled={!data.configured || !data.enabled} loading={sync.isPending}
            onClick={() => sync.mutate(undefined, { onSuccess: (r) => setJob(r.job) })}>Lire Ekylibre</Button>
        </Group>
      </Stack>
    </Paper>
  );
}
