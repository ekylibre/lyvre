// Clôture › Inventaire (lot F4) : charges et produits constatés d'avance proposés depuis les pièces
// dont la période de service dépasse la clôture (factures d'achat, abonnements, factures de vente,
// lignes d'écriture) ; montant modifiable, « Passer les écritures » (extournées à l'ouverture de N+1).
import { useState } from "react";
import { Anchor, Button, Checkbox, Group, Paper, Table, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { MoneyInput, MoneyText } from "../../components/Money";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";

export interface PrepaidProposal {
  key: string; kind: "prepaid_expense" | "deferred_income"; source: "purchase" | "sale" | "line"; url: string; label: string;
  account_code: string; period_start: string; period_end: string; base_cents: number; days_after: number; days_total: number;
  amount_cents: number; posted: boolean;
}

const KINDS = { prepaid_expense: "Charge constatée d'avance", deferred_income: "Produit constaté d'avance" };

export function PrepaidPanel({ fyId, editable }: { fyId: number; editable: boolean }) {
  const key = ["closing", fyId, "prepaid"];
  const { data } = useQuery({ queryKey: key, queryFn: () => api.get<{ items: PrepaidProposal[] }>(`/api/v1/fiscal-years/${fyId}/closing/prepaid`) });
  const [chosen, setChosen] = useState<Record<string, number | null>>({});
  const post = useAction(() => api.post<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fyId}/closing/prepaid`, {
    items: Object.entries(chosen).map(([k, amount]) => ({ key: k, amount_cents: amount ?? undefined })),
  }), { invalidate: [["closing", fyId]] });
  const items = data?.items ?? [];
  if (!items.length) return null;
  return (
    <Paper withBorder p="sm">
      <Text fw={600} size="sm" mb={4}>Propositions de charges et produits constatés d'avance</Text>
      <Text size="xs" c="dimmed" mb="xs">Pièces dont la période dépasse la clôture : part de la période après le dernier jour de l'exercice.</Text>
      <Table>
        <Table.Thead><Table.Tr>{editable && <Table.Th w={36} />}<Table.Th>Pièce</Table.Th><Table.Th>Compte</Table.Th><Table.Th>Période</Table.Th>
          <Table.Th ta="right">Montant de la pièce</Table.Th><Table.Th ta="right">Constaté d'avance</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>
          {items.map((p) => (
            <Table.Tr key={p.key}>
              {editable && <Table.Td>{!p.posted && <Checkbox aria-label={`Retenir ${p.label}`} checked={p.key in chosen}
                onChange={(e) => { const next = { ...chosen }; if (e.currentTarget.checked) next[p.key] = p.amount_cents; else delete next[p.key]; setChosen(next); }} />}</Table.Td>}
              <Table.Td><Anchor component={AppLink} href={p.url} size="sm">{p.label || p.source}</Anchor>
                <Text size="xs" c="dimmed">{KINDS[p.kind]}</Text></Table.Td>
              <Table.Td className="lv-num">{p.account_code}</Table.Td>
              <Table.Td><Text size="sm" className="lv-num">{`${formatDate(p.period_start)} → ${formatDate(p.period_end)}`}</Text>
                <Text size="xs" c="dimmed">{`${p.days_after} / ${p.days_total} jours après la clôture`}</Text></Table.Td>
              <Table.Td ta="right"><MoneyText cents={p.base_cents} /></Table.Td>
              <Table.Td ta="right">{p.posted ? <StatusBadge tone="ok">passée</StatusBadge>
                : p.key in chosen && editable ? <MoneyInput aria-label={`Montant ${p.label}`} value={chosen[p.key]} w={130}
                    onChange={(v) => setChosen({ ...chosen, [p.key]: v })} />
                  : <MoneyText cents={p.amount_cents} />}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      {editable && <Group mt="sm"><Button loading={post.isPending} disabled={!Object.keys(chosen).length}
        onClick={() => post.mutate(undefined, { onSuccess: () => setChosen({}) })}>{`Passer les écritures (${Object.keys(chosen).length})`}</Button></Group>}
    </Paper>
  );
}
