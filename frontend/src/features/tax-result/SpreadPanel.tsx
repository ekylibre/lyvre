// Résultat fiscal › étalement 75-0 A et historique 75-0 B (lot AG6.e, claudedocs/design_fiscalite_ba.md § 7) :
// bénéfice exceptionnel proposé, étalements par septièmes, bénéfices des 3 derniers exercices par associé.
import { useState } from "react";
import { Alert, Button, Group, Paper, Select, Table, Text, TextInput, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { MoneyInput, MoneyText } from "../../components/Money";

type Option = { value: string; label: string };
export interface SpreadView {
  proposal: { base_cents: number; average_cents: number | null; floor_cents: number | null; exceptional_cents: number; reason: string | null;
    previous: { year: number; label: string; fiscal_result_cents: number | null; source: string }[] };
  register: { id: number; origin: string; fiscal_year_id: number; kind_label: string; amount_cents: number; reason: string | null;
    schedule: { rank: number; label: string; amount_cents: number }[] }[];
  kinds: Option[];
  averaging: { labels: string[]; totals: (number | null)[]; average_cents: number | null; option: boolean;
    associates: { associate_id: number; name: string; values: (number | null)[]; average_cents: number | null }[] };
}

const money = (v: number | null) => (v === null ? "—" : <MoneyText cents={v} />);

export function SpreadPanel({ fyId, editable }: { fyId: number; editable: boolean }) {
  const url = `/api/v1/fiscal-years/${fyId}/income-spreads`;
  const { data } = useQuery({ queryKey: ["tax-result", fyId, "spreads"], queryFn: () => api.get<{ item: SpreadView }>(url) });
  const [draft, setDraft] = useState<{ kind: string; amount: number | null; reason: string }>({ kind: "profit", amount: null, reason: "" });
  const [error, setError] = useState<string | null>(null);
  const opts = { invalidate: [["tax-result"]] };
  const add = useAction((b: object) => api.post<{ notices: Notice[] }>(url, b), opts);
  const remove = useAction((id: number) => api.delete<{ notices: Notice[] }>(`${url}/${id}`), opts);
  if (!data?.item) return null;
  const d = data.item;
  const p = d.proposal;
  const run = (x: Promise<unknown>, after?: () => void) => { setError(null); x.then(after, (e) => setError(e instanceof ApiError ? e.message : "Action impossible.")); };
  return (
    <Paper withBorder p="md" mt="lg">
      <Title order={4} mb="xs">Étalement des revenus exceptionnels (art. 75-0 A)</Title>
      {p.reason && <Alert color="gray" mb="xs">{p.reason}</Alert>}
      <Text size="sm">
        Bénéfice avant abattement JA <MoneyText cents={p.base_cents} /> ; moyenne des 3 exercices précédents {money(p.average_cents)}
        {p.floor_cents !== null && <> ; seuil <MoneyText cents={p.floor_cents} /></>} : bénéfice exceptionnel <MoneyText cents={p.exceptional_cents} fw={600} />.
      </Text>
      <Text size="xs" c="dimmed">Exercices précédents : {p.previous.map((x) => `${x.label} ${x.fiscal_result_cents === null ? "inconnu" : (x.fiscal_result_cents / 100).toLocaleString("fr-FR") + " €"}`).join(" · ")}
        {" "}(années antérieures à Lyvre : Structure › Fiscalité).</Text>
      {editable && (
        <Group align="end" gap="xs" mt="sm">
          <Select label="Revenu étalé" w={300} data={d.kinds} value={draft.kind} allowDeselect={false} onChange={(v) => setDraft({ ...draft, kind: v ?? "profit" })} />
          <MoneyInput label="Montant" w={140} value={draft.amount ?? (draft.kind === "profit" && p.exceptional_cents ? p.exceptional_cents : null)}
            onChange={(v) => setDraft({ ...draft, amount: v })} />
          <TextInput label="Motif" w={260} placeholder={draft.kind === "slaughter" ? "indemnité − valeur des animaux" : "facultatif"}
            value={draft.reason} onChange={(e) => setDraft({ ...draft, reason: e.currentTarget.value })} />
          <Button variant="light" loading={add.isPending} onClick={() => run(add.mutateAsync({ kind: draft.kind, reason: draft.reason,
            amount_cents: draft.amount ?? (draft.kind === "profit" ? p.exceptional_cents : null) }), () => setDraft({ kind: "profit", amount: null, reason: "" }))}>Étaler</Button>
        </Group>)}
      {d.register.length > 0 && (
        <Table mt="sm">
          <Table.Thead><Table.Tr><Table.Th>Origine</Table.Th><Table.Th>Revenu</Table.Th><Table.Th ta="right">Montant</Table.Th><Table.Th>Septièmes</Table.Th><Table.Th /></Table.Tr></Table.Thead>
          <Table.Tbody>
            {d.register.map((s) => (
              <Table.Tr key={s.id}><Table.Td>{s.origin}</Table.Td><Table.Td><Text size="sm">{s.kind_label}</Text>{s.reason && <Text size="xs" c="dimmed">{s.reason}</Text>}</Table.Td>
                <Table.Td ta="right"><MoneyText cents={s.amount_cents} /></Table.Td>
                <Table.Td><Text size="xs">{s.schedule.map((x) => `${x.label} : ${(x.amount_cents / 100).toLocaleString("fr-FR")} €`).join(" · ")}</Text></Table.Td>
                <Table.Td>{editable && s.fiscal_year_id === fyId && <Button size="compact-xs" variant="subtle" color="brique" onClick={() => run(remove.mutateAsync(s.id))}>Supprimer</Button>}</Table.Td></Table.Tr>))}
          </Table.Tbody>
        </Table>)}
      {error && <Alert color="brique" mt="sm">{error}</Alert>}

      <Text fw={600} size="sm" mt="md">Historique pour la moyenne triennale (art. 75-0 B){d.averaging.option ? " — option en vigueur" : ""}</Text>
      <Text size="xs" c="dimmed">L'option se déclare au niveau du foyer de chaque associé ; Lyvre fournit les bénéfices.</Text>
      <Table>
        <Table.Thead><Table.Tr><Table.Th />{d.averaging.labels.map((l) => <Table.Th key={l} ta="right">{l}</Table.Th>)}<Table.Th ta="right">Moyenne</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>
          <Table.Tr><Table.Td fw={600}>Exploitation</Table.Td>{d.averaging.totals.map((v, i) => <Table.Td key={i} ta="right">{money(v)}</Table.Td>)}
            <Table.Td ta="right">{money(d.averaging.average_cents)}</Table.Td></Table.Tr>
          {d.averaging.associates.map((a) => (
            <Table.Tr key={a.associate_id}><Table.Td>{a.name}</Table.Td>{a.values.map((v, i) => <Table.Td key={i} ta="right">{money(v)}</Table.Td>)}
              <Table.Td ta="right">{money(a.average_cents)}</Table.Td></Table.Tr>))}
        </Table.Tbody>
      </Table>
    </Paper>
  );
}
