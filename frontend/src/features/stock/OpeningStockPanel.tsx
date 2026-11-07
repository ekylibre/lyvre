// Stock d'entrée au passage du micro-BA au réel (lot CG5.c, BOI-BA-REG-40-10-10 § 190 à 200 et § 470) : lignes du
// stock détenu à la date du changement, valeur la plus faible du prix de revient et du cours du jour, écriture
// d'ouverture (108 ou comptes courants d'associés) à valider, note du stock initial à joindre à la déclaration.
import { useState } from "react";
import { Alert, Button, Group, NumberInput, Paper, Select, Table, Text, TextInput, Textarea, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { MoneyInput, MoneyText } from "../../components/Money";

type Option = { value: string; label: string };
interface OpeningLine { id: number; account_code: string; label: string; quantity: string; unit: string; method: string;
  method_label: string; cost_unit_cents: number | null; market_unit_cents: number | null; amount_cents: number | null;
  value_cents: number | null }
interface OpeningStock { applies: boolean; lines: OpeningLine[]; total_cents: number; frozen: boolean; note: string | null;
  entry: { id: number; validated: boolean } | null; methods: Option[] }
type Draft = { account_code: string; label: string; quantity: number | string; unit: string; method: string;
  cost_unit_cents: number | null; market_unit_cents: number | null; amount_cents: number | null };

const EMPTY: Draft = { account_code: "", label: "", quantity: "", unit: "t", method: "lower", cost_unit_cents: null,
  market_unit_cents: null, amount_cents: null };

export function OpeningStockPanel({ fyId, units, editable }: { fyId: number; units: Option[]; editable: boolean }) {
  const key = ["stock", "opening", fyId];
  const { data } = useQuery({ queryKey: key, queryFn: () => api.get<{ item: OpeningStock }>(`/api/v1/fiscal-years/${fyId}/opening-stock`) });
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const opts = { invalidate: [key, ["stock"]] };
  const add = useAction((body: Draft) => api.post<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fyId}/opening-stock/lines`,
    { ...body, quantity: String(body.quantity || 0) }), opts);
  const remove = useAction((id: number) => api.delete<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fyId}/opening-stock/lines/${id}`), opts);
  const post = useAction(() => api.post<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fyId}/opening-stock/entry`, {}), opts);
  const run = (p: Promise<unknown>, after?: () => void) => {
    setError(null); p.then(after, (e) => setError(e instanceof ApiError ? e.message : "Action impossible."));
  };
  const item = data?.item;
  if (!item?.applies) return null;
  const crop = draft.method === "crop_advance";
  const canEdit = editable && !item.frozen;
  return (
    <Paper withBorder p="md" mb="md">
      <Title order={4}>Stock d'entrée au passage au réel</Title>
      <Text size="sm" c="dimmed" mb="xs">Stock détenu à la date du changement de régime : prix de revient, ou cours du jour s'il est
        inférieur ; avances aux cultures au prix de revient. Valeur figée ensuite (BOI-BA-REG-40-10-10 § 190 à 200).</Text>
      {item.lines.length > 0 && (
        <Table fz="sm" mb="xs">
          <Table.Thead><Table.Tr><Table.Th>Compte</Table.Th><Table.Th>Produit</Table.Th><Table.Th>Évaluation</Table.Th>
            <Table.Th ta="right">Valeur</Table.Th><Table.Th /></Table.Tr></Table.Thead>
          <Table.Tbody>{item.lines.map((l) => (
            <Table.Tr key={l.id}><Table.Td>{l.account_code}</Table.Td><Table.Td>{l.label} {l.method !== "crop_advance" && `(${l.quantity} ${l.unit})`}</Table.Td>
              <Table.Td><Text size="xs">{l.method_label}</Text></Table.Td>
              <Table.Td ta="right">{l.value_cents === null ? "à compléter" : <MoneyText cents={l.value_cents} />}</Table.Td>
              <Table.Td>{canEdit && <Button size="compact-xs" variant="subtle" color="brique" onClick={() => run(remove.mutateAsync(l.id))}>Retirer</Button>}</Table.Td>
            </Table.Tr>))}
          </Table.Tbody>
        </Table>)}
      <Text size="sm" mb="xs">Total : <MoneyText cents={item.total_cents} />
        {item.entry ? (item.entry.validated ? " · écriture d'ouverture validée (figée)" : " · écriture d'ouverture passée, à valider") : ""}</Text>
      {canEdit && (
        <Group align="end" gap="xs" mb="xs">
          <TextInput label="Compte" w={90} value={draft.account_code} onChange={(e) => setDraft({ ...draft, account_code: e.currentTarget.value })} />
          <TextInput label="Produit" w={160} value={draft.label} onChange={(e) => setDraft({ ...draft, label: e.currentTarget.value })} />
          <Select label="Évaluation" w={220} data={item.methods} value={draft.method} allowDeselect={false}
            onChange={(v) => setDraft({ ...draft, method: v ?? "lower" })} />
          {crop ? <MoneyInput label="Montant" w={130} value={draft.amount_cents} onChange={(v) => setDraft({ ...draft, amount_cents: v })} /> : (
            <>
              <NumberInput label="Quantité" w={100} decimalSeparator="," value={draft.quantity} onChange={(v) => setDraft({ ...draft, quantity: v })} />
              <Select label="Unité" w={100} data={units} value={draft.unit} allowDeselect={false} onChange={(v) => setDraft({ ...draft, unit: v ?? "t" })} />
              <MoneyInput label="Prix de revient unitaire" w={150} value={draft.cost_unit_cents} onChange={(v) => setDraft({ ...draft, cost_unit_cents: v })} />
              <MoneyInput label="Cours du jour unitaire" w={150} value={draft.market_unit_cents} onChange={(v) => setDraft({ ...draft, market_unit_cents: v })} />
            </>)}
          <Button variant="light" disabled={!draft.account_code || !draft.label} loading={add.isPending}
            onClick={() => run(add.mutateAsync(draft), () => setDraft(EMPTY))}>Ajouter</Button>
        </Group>)}
      {canEdit && item.lines.length > 0 && (
        <Button size="sm" loading={post.isPending} onClick={() => run(post.mutateAsync(undefined))}>
          {item.entry ? "Repasser l'écriture d'ouverture" : "Passer l'écriture d'ouverture"}</Button>)}
      {error && <Alert color="brique" mt="xs">{error}</Alert>}
      {item.note && <Textarea mt="sm" label="Note du stock initial (à joindre à la première déclaration au réel, § 470)"
        readOnly autosize minRows={3} value={item.note} />}
    </Paper>
  );
}
