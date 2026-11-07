// Résultat fiscal › DEP (lot AG6.c, claudedocs/design_fiscalite_ba.md § 5) : plafond sur le bénéfice après abattement
// JA, déduction de l'exercice (extra-comptable), épargne (comptes repérés, substituts) et ratio, registre par exercice
// d'origine avec utilisations (aléa : 30 % exonérés) et réintégrations, valeur ajoutée pour l'aléa économique.
import { useState } from "react";
import { Alert, Button, Checkbox, Group, Paper, Select, SimpleGrid, Table, Text, TextInput, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { MoneyInput, MoneyText } from "../../components/Money";
import { formatDate } from "../../lib/format";

type Option = { value: string; label: string };
export interface DepView {
  base_cents: number; base_basis?: "before_ja" | "after_ja"; base_notes?: string[]; deduction_cents: number;
  ceiling: { ceiling_cents: number; per_operator_cents?: number; operators?: number; pending_cents?: number; error?: string };
  register: { id: number; kind_label: string; origin: string; amount_cents: number; outstanding_cents: number; deadline: string; deadline_now: boolean;
    movements: { id: number; kind_label: string; on: string; amount_cents: number; exempt_cents: number; reason: string | null; fiscal_year_id: number }[] }[];
  savings: { accounts: { id: number; label: string }[]; at_close_cents: number; at_deadline_cents: number; deadline: string; substitutes_cents: number;
    substitutes: { id: number; label: string; amount_cents: number }[]; savings_cents: number; pending_cents: number; minimum_cents: number;
    ratio_bp: number | null; below: boolean; above: boolean; deadline_passed: boolean; deadline_basis?: "six_months" | "filing" };
  hazard: { value_added_cents: number; average3_cents: number | null; drop3_bp: number | null; hazard: boolean };
  movements: Option[]; hazards: Option[];
}

export function DepPanel({ fyId, editable }: { fyId: number; editable: boolean }) {
  const url = `/api/v1/fiscal-years/${fyId}/dep`;
  const { data } = useQuery({ queryKey: ["tax-result", fyId, "dep"], queryFn: () => api.get<{ item: DepView }>(url) });
  const { data: banks } = useQuery({ queryKey: ["bank-accounts", "dep"], enabled: editable,
    queryFn: () => api.get<{ items: { id: number; label: string; kind: string; dep_savings?: boolean }[] }>("/api/v1/bank-accounts") });
  const [amount, setAmount] = useState<number | null>(null);
  const [move, setMove] = useState<{ entry: string | null; kind: string; on: string; amount: number | null; hazard: string | null; reason: string }>(
    { entry: null, kind: "use", on: "", amount: null, hazard: null, reason: "" });
  const [sub, setSub] = useState<{ label: string; amount: number | null }>({ label: "", amount: null });
  const [error, setError] = useState<string | null>(null);
  const opts = { invalidate: [["tax-result"], ["bank-accounts"]] };
  const setDep = useAction((b: object) => api.put<{ notices: Notice[] }>(url, b), opts);
  const addMove = useAction((b: object) => api.post<{ notices: Notice[] }>(`${url}/movements`, b), opts);
  const delMove = useAction((id: number) => api.delete<{ notices: Notice[] }>(`${url}/movements/${id}`), opts);
  const addSub = useAction((b: object) => api.post<{ notices: Notice[] }>(`${url}/substitutes`, b), opts);
  const delSub = useAction((id: number) => api.delete<{ notices: Notice[] }>(`${url}/substitutes/${id}`), opts);
  const flag = useAction((v: { id: number; on: boolean }) => api.put<{ notices: Notice[] }>(`/api/v1/bank-accounts/${v.id}/dep-savings`, { dep_savings: v.on }), opts);
  if (!data) return null;
  const d = data.item;
  const run = (p: Promise<unknown>, after?: () => void) => { setError(null); p.then(after, (e) => setError(e instanceof ApiError ? e.message : "Action impossible.")); };
  return (
    <Paper withBorder p="md" mt="lg">
      <Title order={4} mb="xs">Déduction pour épargne de précaution (DEP)</Title>
      {d.ceiling.error && <Alert color="paille" mb="xs">{d.ceiling.error}</Alert>}
      <SimpleGrid cols={{ base: 2, sm: 4 }} mb="sm">
        <div><Text size="xs" c="dimmed">{d.base_basis === "before_ja" ? "Bénéfice avant abattement JA (société)" : "Bénéfice après abattement JA"}</Text><MoneyText cents={d.base_cents} /></div>
        <div><Text size="xs" c="dimmed">Plafond{d.ceiling.operators && d.ceiling.operators > 1 ? ` (× ${d.ceiling.operators})` : ""}</Text><MoneyText cents={d.ceiling.ceiling_cents} /></div>
        <div><Text size="xs" c="dimmed">DEP de l'exercice</Text><MoneyText cents={d.deduction_cents} /></div>
        <div><Text size="xs" c="dimmed">Déductions non rapportées</Text><MoneyText cents={d.savings.pending_cents} /></div>
      </SimpleGrid>
      {(d.base_notes ?? []).map((n) => <Alert key={n} color="paille" mb="xs">{n}</Alert>)}
      {editable && (
        <Group align="end" gap="xs" mb="md">
          <MoneyInput label="DEP de l'exercice" w={160} value={amount ?? d.deduction_cents} onChange={setAmount} />
          <Button size="sm" loading={setDep.isPending} onClick={() => run(setDep.mutateAsync({ amount_cents: amount ?? d.deduction_cents }), () => setAmount(null))}>Enregistrer</Button>
        </Group>)}

      <Text fw={600} size="sm">Épargne</Text>
      <Text size="sm" c={d.savings.below ? "var(--lv-brique-ink)" : undefined}>
        Comptes repérés : <MoneyText cents={d.savings.at_close_cents} /> à la clôture, <MoneyText cents={d.savings.at_deadline_cents} /> au {formatDate(d.savings.deadline)}{d.savings.deadline_basis === "filing" ? " (date limite de dépôt de la liasse)" : ""} ;
        substituts <MoneyText cents={d.savings.substitutes_cents} /> — épargne retenue <MoneyText cents={d.savings.savings_cents} />
        {d.savings.ratio_bp !== null && ` (${(d.savings.ratio_bp / 100).toLocaleString("fr-FR")} %)`} ; minimum <MoneyText cents={d.savings.minimum_cents} />.
      </Text>
      {editable && (banks?.items ?? []).filter((b) => b.kind === "bank").map((b) => (
        <Checkbox key={b.id} mt={4} label={`${b.label} : compte d'épargne DEP`} checked={!!b.dep_savings}
          onChange={(e) => run(flag.mutateAsync({ id: b.id, on: e.currentTarget.checked }))} />))}
      {d.savings.substitutes.map((s) => (
        <Group key={s.id} gap="xs"><Text size="sm">{s.label} : <MoneyText cents={s.amount_cents} /></Text>
          {editable && <Button size="compact-xs" variant="subtle" color="brique" onClick={() => run(delSub.mutateAsync(s.id))}>Retirer</Button>}</Group>))}
      {editable && (
        <Group align="end" gap="xs" mt="xs" mb="md">
          <TextInput label="Substitut d'épargne" placeholder="stock de fourrage consommé…" w={260} value={sub.label} onChange={(e) => setSub({ ...sub, label: e.currentTarget.value })} />
          <MoneyInput label="Montant" w={130} value={sub.amount} onChange={(v) => setSub({ ...sub, amount: v })} />
          <Button variant="light" disabled={!sub.label || !sub.amount} onClick={() => run(addSub.mutateAsync({ label: sub.label, amount_cents: sub.amount }), () => setSub({ label: "", amount: null }))}>Ajouter</Button>
        </Group>)}

      <Text fw={600} size="sm" mt="sm">Registre</Text>
      <Table>
        <Table.Thead><Table.Tr><Table.Th>Origine</Table.Th><Table.Th ta="right">Montant</Table.Th><Table.Th ta="right">Non rapporté</Table.Th><Table.Th>Échéance</Table.Th><Table.Th>Mouvements</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>
          {d.register.map((e) => (
            <Table.Tr key={e.id}>
              <Table.Td>{e.kind_label} {e.origin}</Table.Td>
              <Table.Td ta="right"><MoneyText cents={e.amount_cents} /></Table.Td>
              <Table.Td ta="right"><MoneyText cents={e.outstanding_cents} /></Table.Td>
              <Table.Td>{e.deadline}{e.deadline_now && <Text span size="xs" c="var(--lv-brique-ink)"> · cet exercice</Text>}</Table.Td>
              <Table.Td>{e.movements.map((m) => (
                <Text key={m.id} size="xs">{formatDate(m.on)} {m.kind_label} <MoneyText cents={m.amount_cents} />
                  {m.exempt_cents ? <> (exonéré <MoneyText cents={m.exempt_cents} />)</> : null}
                  {editable && m.fiscal_year_id === fyId && <Button size="compact-xs" variant="subtle" color="brique" onClick={() => run(delMove.mutateAsync(m.id))}>×</Button>}</Text>))}</Table.Td>
            </Table.Tr>))}
        </Table.Tbody>
      </Table>
      {editable && d.register.length > 0 && (
        <Group align="end" gap="xs" mt="xs">
          <Select label="Déduction" w={160} data={d.register.map((e) => ({ value: String(e.id), label: `${e.kind_label} ${e.origin}` }))} value={move.entry} onChange={(v) => setMove({ ...move, entry: v })} />
          <Select label="Mouvement" w={140} data={d.movements} value={move.kind} allowDeselect={false} onChange={(v) => setMove({ ...move, kind: v ?? "use" })} />
          <TextInput label="Date" type="date" w={140} value={move.on} onChange={(e) => setMove({ ...move, on: e.currentTarget.value })} />
          <MoneyInput label="Montant" w={120} value={move.amount} onChange={(v) => setMove({ ...move, amount: v })} />
          {move.kind === "use" && <Select label="Aléa" w={200} clearable data={d.hazards} value={move.hazard} onChange={(v) => setMove({ ...move, hazard: v })} />}
          <TextInput label="Motif" w={160} value={move.reason} onChange={(e) => setMove({ ...move, reason: e.currentTarget.value })} />
          <Button variant="light" disabled={!move.entry || !move.amount || !move.on} onClick={() => run(addMove.mutateAsync({
            entry_id: Number(move.entry), kind: move.kind, on: move.on, amount_cents: move.amount, hazard: move.hazard, reason: move.reason }),
          () => setMove({ ...move, amount: null, reason: "" }))}>Ajouter</Button>
        </Group>)}
      <Text size="xs" c="dimmed" mt="sm">Valeur ajoutée de l'exercice <MoneyText cents={d.hazard.value_added_cents} />
        {d.hazard.average3_cents !== null && <> ; moyenne des 3 exercices précédents <MoneyText cents={d.hazard.average3_cents} /> (baisse {((d.hazard.drop3_bp ?? 0) / 100).toLocaleString("fr-FR")} %)</>}
        {d.hazard.hazard && " — aléa économique possible (attestation de l'expert-comptable)"}.</Text>
      {error && <Alert color="brique" mt="xs">{error}</Alert>}
    </Paper>
  );
}
