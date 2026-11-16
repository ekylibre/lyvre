// Clôture › Inventaire (lot AG5.c) : dépréciation des biens vivants — montant cumulé voulu au bilan (294) par fiche,
// avec motif ; l'écriture passe la différence avec la clôture précédente (68164, ou reprise en 78164) ; un bien sorti
// voit sa dépréciation reprise.
import { useState } from "react";
import { Alert, Anchor, Button, Group, Paper, Table, Text, TextInput } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { AppLink } from "../../app/navigation";
import { MoneyInput, MoneyText } from "../../components/Money";

interface ImpairmentRow { asset_id: number; label: string; account_code: string; net_cents: number; previous_cents: number;
  amount_cents: number; delta_cents: number; reason: string | null; exited: boolean; saved: boolean; posted: boolean }
interface Impairments { items: ImpairmentRow[]; enabled: boolean; entry: { id: number; reference: string } | null }

export function LivingImpairmentPanel({ fyId, editable }: { fyId: number; editable: boolean }) {
  const url = `/api/v1/fiscal-years/${fyId}/closing/living-impairments`;
  const { data } = useQuery({ queryKey: ["closing", fyId, "living-impairments"], queryFn: () => api.get<Impairments>(url) });
  const [drafts, setDrafts] = useState<Record<number, { amount: number | null; reason: string }>>({});
  const [error, setError] = useState<string | null>(null);
  const opts = { invalidate: [["closing", fyId]] };
  const save = useAction((b: object) => api.put<{ notices: Notice[] }>(`${url}/values`, b), opts);
  const post = useAction(() => api.post<{ notices: Notice[] }>(url), opts);
  const cancel = useAction(() => api.delete<{ notices: Notice[] }>(url), opts);
  if (!data?.enabled || data.items.length === 0) return null;
  const run = (p: Promise<unknown>) => { setError(null); p.catch((e) => setError(e instanceof ApiError ? e.message : "Action impossible.")); };
  const locked = !!data.entry || !editable;
  return (
    <Paper withBorder p="sm">
      <Text fw={600} size="sm" mb={4}>Dépréciation des biens vivants</Text>
      <Text size="xs" c="dimmed" mb="xs">Dépréciation cumulée voulue au bilan (294) ; l'écriture passe l'écart avec la clôture précédente.</Text>
      <Table>
        <Table.Tbody>
          {data.items.map((r) => {
            const d = drafts[r.asset_id] ?? { amount: r.amount_cents, reason: r.reason ?? "" };
            const set = (patch: Partial<typeof d>) => setDrafts({ ...drafts, [r.asset_id]: { ...d, ...patch } });
            return (
              <Table.Tr key={r.asset_id}>
                <Table.Td><Anchor component={AppLink} href={`/assets/${r.asset_id}`} size="sm">{r.label}</Anchor>
                  <Text size="xs" c="dimmed">{r.account_code} · valeur nette <MoneyText cents={r.net_cents} /> · précédente <MoneyText cents={r.previous_cents} />
                    {r.exited && " · sorti : reprise"}</Text></Table.Td>
                <Table.Td>{locked || r.exited ? <MoneyText cents={r.amount_cents} />
                  : <MoneyInput aria-label={`Dépréciation ${r.label}`} w={120} value={d.amount} onChange={(v) => set({ amount: v })} />}</Table.Td>
                <Table.Td>{locked || r.exited ? <Text size="xs">{r.reason}</Text>
                  : <TextInput aria-label={`Motif ${r.label}`} w={200} placeholder="motif" value={d.reason} onChange={(e) => set({ reason: e.currentTarget.value })} />}</Table.Td>
                <Table.Td ta="right">{r.delta_cents ? <MoneyText cents={r.delta_cents} plus /> : null}
                  {!locked && !r.exited && <Button size="compact-sm" variant="light" ml="xs"
                    onClick={() => run(save.mutateAsync({ asset_id: r.asset_id, amount_cents: d.amount ?? 0, reason: d.reason }))}>Enregistrer</Button>}</Table.Td>
              </Table.Tr>);
          })}
        </Table.Tbody>
      </Table>
      {data.entry && <Text size="sm" mt="xs">Écriture <Anchor component={AppLink} href={`/entries/${data.entry.id}`}>{data.entry.reference}</Anchor>.</Text>}
      {editable && (
        <Group mt="xs" gap="xs">
          <Button size="xs" loading={post.isPending} onClick={() => run(post.mutateAsync(undefined))}>{data.entry ? "Repasser" : "Passer les dépréciations"}</Button>
          {data.entry && <Button size="xs" variant="subtle" color="brique" onClick={() => run(cancel.mutateAsync(undefined))}>Annuler l'écriture</Button>}
        </Group>)}
      {error && <Alert color="brique" mt="xs">{error}</Alert>}
    </Paper>
  );
}
