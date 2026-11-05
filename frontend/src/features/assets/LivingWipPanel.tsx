// Clôture › Inventaire (lot AG5.b, claudedocs/design_biens_vivants.md § 4) : biens vivants en cours (234x) — coûts de
// croissance de l'exercice portés en en-cours, D 234x / C 7222 au dernier jour, non extournés ; la mise en service
// (fiche de l'immobilisation) vire ensuite le cumul en 24x.
import { useState } from "react";
import { Alert, Anchor, Button, Group, Paper, Table, Text, TextInput } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { AppLink } from "../../app/navigation";
import { MoneyInput, MoneyText } from "../../components/Money";
import { StatusBadge } from "../../components/StatusBadge";

export interface LivingWipRow {
  asset_id: number; label: string; account_code: string; status: string; acquisition_cents: number; units: number | null;
  species: string | null; amount_cents: number | null; basis: string | null; posted: boolean;
}
interface LivingWip { items: LivingWipRow[]; enabled: boolean; entry: { id: number; reference: string } | null }

export function LivingWipPanel({ fyId, editable }: { fyId: number; editable: boolean }) {
  const url = `/api/v1/fiscal-years/${fyId}/closing/living-wip`;
  const { data } = useQuery({ queryKey: ["closing", fyId, "living-wip"], queryFn: () => api.get<LivingWip>(url) });
  const [drafts, setDrafts] = useState<Record<number, { amount: number | null; basis: string }>>({});
  const [error, setError] = useState<string | null>(null);
  const opts = { invalidate: [["closing", fyId], ["assets"]] };
  const save = useAction((b: object) => api.put<{ notices: Notice[] }>(`${url}/costs`, b), opts);
  const post = useAction(() => api.post<{ notices: Notice[] }>(url), opts);
  const cancel = useAction(() => api.delete<{ notices: Notice[] }>(url), opts);
  if (!data?.enabled || data.items.length === 0) return null;
  const run = (p: Promise<unknown>, after?: () => void) => { setError(null); p.then(after, (e) => setError(e instanceof ApiError ? e.message : "Action impossible.")); };
  const locked = !!data.entry || !editable;
  return (
    <Paper withBorder p="sm">
      <Text fw={600} size="sm" mb={4}>Biens vivants en cours</Text>
      <Text size="xs" c="dimmed" mb="xs">Coûts de croissance de l'exercice (animaux, plantations pas encore en production) portés en 234x
        contre 7222, au dernier jour ; ils s'ajoutent à la valeur de la fiche, virée en 24x à la mise en service.</Text>
      <Table>
        <Table.Tbody>
          {data.items.map((r) => {
            const d = drafts[r.asset_id] ?? { amount: r.amount_cents, basis: r.basis ?? "" };
            const set = (patch: Partial<typeof d>) => setDrafts({ ...drafts, [r.asset_id]: { ...d, ...patch } });
            return (
              <Table.Tr key={r.asset_id}>
                <Table.Td><Anchor component={AppLink} href={`/assets/${r.asset_id}`} size="sm">{r.label}</Anchor>
                  <Text size="xs" c="dimmed">{r.account_code}{r.units ? ` · ${r.units} ${r.species ?? ""}` : ""} · valeur <MoneyText cents={r.acquisition_cents} /></Text></Table.Td>
                <Table.Td>{locked ? (r.amount_cents !== null ? <MoneyText cents={r.amount_cents} /> : "—")
                  : <MoneyInput aria-label={`Coût de croissance ${r.label}`} w={130} value={d.amount} onChange={(v) => set({ amount: v })} />}</Table.Td>
                <Table.Td>{locked ? <Text size="xs">{r.basis}</Text>
                  : <TextInput aria-label={`Base ${r.label}`} placeholder="base (coût réel, barème)" w={220} value={d.basis} onChange={(e) => set({ basis: e.currentTarget.value })} />}</Table.Td>
                <Table.Td ta="right">{r.posted ? <StatusBadge tone="ok">passé</StatusBadge> : !locked && (
                  <Button size="compact-sm" variant="light" onClick={() => run(save.mutateAsync({ asset_id: r.asset_id, amount_cents: d.amount, basis: d.basis }))}>Enregistrer</Button>)}</Table.Td>
              </Table.Tr>);
          })}
        </Table.Tbody>
      </Table>
      {data.entry && <Text size="sm" mt="xs">Écriture <Anchor component={AppLink} href={`/entries/${data.entry.id}`}>{data.entry.reference}</Anchor>.</Text>}
      {editable && (
        <Group mt="xs" gap="xs">
          <Button size="xs" loading={post.isPending} disabled={!data.items.some((r) => r.amount_cents)} onClick={() => run(post.mutateAsync(undefined))}>
            {data.entry ? "Repasser les en-cours" : "Passer les en-cours"}</Button>
          {data.entry && <Button size="xs" variant="subtle" color="brique" onClick={() => run(cancel.mutateAsync(undefined))}>Annuler l'écriture</Button>}
        </Group>)}
      {error && <Alert color="brique" mt="xs">{error}</Alert>}
    </Paper>
  );
}
