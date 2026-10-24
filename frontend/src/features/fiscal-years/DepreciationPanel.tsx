// Clôture › Inventaire (lot F5) : dotations aux amortissements de l'exercice, passées en une
// écriture OD au dernier jour (gérée par l'assistant), repassées tant que l'exercice est ouvert.
import { Anchor, Button, Group, Paper, Table, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { MoneyText } from "../../components/Money";
import { StatusBadge } from "../../components/StatusBadge";
import { AppLink } from "../../app/navigation";

interface Row { asset_id: number; label: string; account_code: string; depreciation_account_code: string | null; days: number; amount_cents: number; posted: boolean }

export function DepreciationPanel({ fyId, editable }: { fyId: number; editable: boolean }) {
  const key = ["closing", fyId, "depreciation"];
  const { data } = useQuery({ queryKey: key, queryFn: () => api.get<{ items: Row[]; enabled: boolean; entry: { id: number; reference: string } | null }>(
    `/api/v1/fiscal-years/${fyId}/closing/depreciation`) });
  const post = useAction(() => api.post<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fyId}/closing/depreciation`, {}),
    { invalidate: [["closing", fyId], ["assets"]] });
  if (!data || (!data.items.length && !data.entry)) return null;
  const total = data.items.reduce((s, r) => s + r.amount_cents, 0);
  return (
    <Paper withBorder p="sm">
      <Group justify="space-between" mb="xs">
        <Text fw={600} size="sm">Dotations aux amortissements</Text>
        {data.entry && <Anchor component={AppLink} href={`/entries/${data.entry.id}`} size="sm">{data.entry.reference}</Anchor>}
      </Group>
      {!data.enabled ? <Text size="sm" c="dimmed">Registre seulement : amortissements non comptabilisés pour cette structure.</Text> : <>
        <Table>
          <Table.Thead><Table.Tr><Table.Th>Immobilisation</Table.Th><Table.Th>Comptes</Table.Th><Table.Th ta="right">Jours</Table.Th><Table.Th ta="right">Dotation</Table.Th><Table.Th /></Table.Tr></Table.Thead>
          <Table.Tbody>{data.items.map((r) => (
            <Table.Tr key={r.asset_id}><Table.Td><Anchor component={AppLink} href={`/assets/${r.asset_id}`} size="sm">{r.label}</Anchor></Table.Td>
              <Table.Td className="lv-num">{`${r.account_code} / ${r.depreciation_account_code ?? "28…"}`}</Table.Td>
              <Table.Td ta="right" className="lv-num">{r.days}</Table.Td><Table.Td ta="right"><MoneyText cents={r.amount_cents} /></Table.Td>
              <Table.Td>{r.posted && <StatusBadge tone="ok">passée</StatusBadge>}</Table.Td></Table.Tr>
          ))}</Table.Tbody>
          <Table.Tfoot><Table.Tr><Table.Th colSpan={3}>Total</Table.Th><Table.Th ta="right"><MoneyText cents={total} /></Table.Th><Table.Th /></Table.Tr></Table.Tfoot>
        </Table>
        {editable && <Group mt="sm"><Button loading={post.isPending} onClick={() => post.mutate(undefined)}>
          {data.entry ? "Recalculer les dotations" : "Passer les dotations"}</Button></Group>}
      </>}
    </Paper>
  );
}
