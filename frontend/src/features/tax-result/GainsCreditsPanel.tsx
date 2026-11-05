// Résultat fiscal › plus-values et crédits d'impôt (lot AG6.g, claudedocs/design_fiscalite_ba.md § 9) : plus-values de
// l'exercice par bien (court / long terme), simulation 151 septies, crédits bio / HVE / remplacement par associé.
import { useState } from "react";
import { Alert, Badge, Button, Checkbox, Group, Paper, Select, SimpleGrid, Table, Text, TextInput, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { MoneyInput, MoneyText } from "../../components/Money";
import { formatDate } from "../../lib/format";

type Option = { value: string; label: string };
export interface GainsView {
  disposals: { asset_id: number; label: string; account: string; acquired_on: string; disposed_on: string; net_cents: number; price_cents: number;
    gain_cents: number; short_cents: number; long_cents: number; long_held: boolean; excluded: boolean; excluded_reason: string | null }[];
  short_cents: number; long_cents: number; long_exempt_cents: number; long_taxable_cents: number; short_exempt_cents: number;
  septies: { activity_since: string | null; young_farmer_buyer: boolean; average_cents: number | null; rate_bp: number | null; detail: string;
    reason: string | null; applied: boolean; associates: { associate_id: number; name: string; receipts_cents: number | null; rate_bp: number | null }[] };
}
export interface CreditsView {
  items: { id: number; kind: string; label: string; data: Record<string, number | string>; amount_cents: number; detail: string;
    share_bp?: number | null; associates: { associate_id: number; name: string; amount_cents: number }[] }[];
  total_cents: number; kinds: Option[]; notes: string[];
}

const pct = (bp: number | null | undefined) => (bp === null || bp === undefined ? "—" : `${(bp / 100).toLocaleString("fr-FR")} %`);

export function GainsCreditsPanel({ fyId, editable }: { fyId: number; editable: boolean }) {
  const base = `/api/v1/fiscal-years/${fyId}`;
  const gains = useQuery({ queryKey: ["tax-result", fyId, "gains"], queryFn: () => api.get<{ item: GainsView }>(`${base}/capital-gains`) });
  const credits = useQuery({ queryKey: ["tax-result", fyId, "credits"], queryFn: () => api.get<{ item: CreditsView }>(`${base}/tax-credits`) });
  const [draft, setDraft] = useState<{ kind: string; a: number | null; b: string; date: string }>({ kind: "organic", a: null, b: "", date: "" });
  const [error, setError] = useState<string | null>(null);
  const opts = { invalidate: [["tax-result"]] };
  const choose = useAction((b: object) => api.put<{ notices: Notice[] }>(`${base}/capital-gains`, b), opts);
  const saveCredit = useAction((v: { kind: string; body: object }) => api.put<{ notices: Notice[] }>(`${base}/tax-credits/${v.kind}`, v.body), opts);
  const dropCredit = useAction((kind: string) => api.delete<{ notices: Notice[] }>(`${base}/tax-credits/${kind}`), opts);
  const g = gains.data?.item;
  const c = credits.data?.item;
  if (!g || !c) return null;
  const run = (p: Promise<unknown>, after?: () => void) => { setError(null); p.then(after, (e) => setError(e instanceof ApiError ? e.message : "Action impossible.")); };
  const s = g.septies;
  const creditBody = () => draft.kind === "organic" ? { organic_receipts_cents: draft.a }
    : draft.kind === "hve" ? { certified_on: draft.date } : { expense_cents: draft.a, days: Number(draft.b) || null };
  return (
    <Paper withBorder p="md" mt="lg">
      <Title order={4} mb="xs">Plus-values professionnelles</Title>
      {g.disposals.length === 0 ? <Text size="sm" c="dimmed">Aucune cession d'immobilisation dans l'exercice.</Text> : (
        <Table mb="sm">
          <Table.Thead><Table.Tr><Table.Th>Bien</Table.Th><Table.Th>Cédé le</Table.Th><Table.Th ta="right">Valeur nette</Table.Th><Table.Th ta="right">Prix</Table.Th>
            <Table.Th ta="right">Court terme</Table.Th><Table.Th ta="right">Long terme</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {g.disposals.map((d) => (
              <Table.Tr key={d.asset_id}><Table.Td><Text size="sm">{d.account} {d.label}</Text>
                {d.excluded && <Badge size="xs" color="gray">{d.excluded_reason}</Badge>}{!d.long_held && <Text size="xs" c="dimmed">détenu moins de 2 ans</Text>}</Table.Td>
                <Table.Td className="lv-num">{formatDate(d.disposed_on)}</Table.Td>
                <Table.Td ta="right"><MoneyText cents={d.net_cents} /></Table.Td><Table.Td ta="right"><MoneyText cents={d.price_cents} /></Table.Td>
                <Table.Td ta="right"><MoneyText cents={d.short_cents} /></Table.Td><Table.Td ta="right"><MoneyText cents={d.long_cents} /></Table.Td></Table.Tr>))}
          </Table.Tbody>
        </Table>)}
      <Text size="sm">Nets : court terme <MoneyText cents={g.short_cents} />, long terme <MoneyText cents={g.long_cents} />
        {g.long_cents > 0 && <> (imposable à part <MoneyText cents={g.long_taxable_cents} />, exonéré <MoneyText cents={g.long_exempt_cents} />)</>}.</Text>
      <Text fw={600} size="sm" mt="sm">Exonération de l'art. 151 septies</Text>
      {s.reason && <Alert color="gray" my="xs">{s.reason}</Alert>}
      <Text size="sm">Recettes moyennes des 2 années précédentes {s.average_cents !== null ? <MoneyText cents={s.average_cents} /> : "inconnues"} : taux {pct(s.rate_bp)} ({s.detail}).</Text>
      {s.associates.length > 0 && <Text size="xs" c="dimmed">{s.associates.map((a) => `${a.name} : ${pct(a.rate_bp)}`).join(" · ")}</Text>}
      {editable && (
        <Group gap="md" mt="xs" align="end">
          <Checkbox label="Appliquer l'exonération" checked={s.applied} onChange={(e) => run(choose.mutateAsync({ apply_151_septies: e.currentTarget.checked }))} />
          <Checkbox label="Cession à un jeune agriculteur" checked={s.young_farmer_buyer} onChange={(e) => run(choose.mutateAsync({ young_farmer_buyer: e.currentTarget.checked }))} />
          <TextInput label="Début d'activité" type="date" w={170} value={s.activity_since ?? ""} onChange={(e) => run(choose.mutateAsync({ activity_since: e.currentTarget.value || null }))} />
        </Group>)}

      <Title order={4} mt="lg" mb="xs">Crédits d'impôt</Title>
      {c.items.map((i) => (
        <Group key={i.kind} justify="space-between" mb={4}>
          <div><Text size="sm">{i.label} : <MoneyText cents={i.amount_cents} fw={600} /></Text>
            <Text size="xs" c="dimmed">{i.detail}{i.associates.length ? ` — ${i.associates.map((a) => `${a.name} ${(a.amount_cents / 100).toLocaleString("fr-FR")} €`).join(", ")}` : ""}</Text></div>
          {editable && <Button size="compact-xs" variant="subtle" color="brique" onClick={() => run(dropCredit.mutateAsync(i.kind))}>Retirer</Button>}
        </Group>))}
      {editable && (
        <SimpleGrid cols={{ base: 1, sm: 4 }} mt="xs">
          <Select label="Crédit" data={c.kinds} value={draft.kind} allowDeselect={false} onChange={(v) => setDraft({ kind: v ?? "organic", a: null, b: "", date: "" })} />
          {draft.kind === "hve" ? <TextInput label="Certifié le" type="date" value={draft.date} onChange={(e) => setDraft({ ...draft, date: e.currentTarget.value })} />
            : <MoneyInput label={draft.kind === "organic" ? "Recettes bio de l'exercice" : "Dépenses de remplacement"} value={draft.a} onChange={(v) => setDraft({ ...draft, a: v })} />}
          {draft.kind === "replacement" ? <TextInput label="Jours de remplacement" inputMode="numeric" value={draft.b} onChange={(e) => setDraft({ ...draft, b: e.currentTarget.value })} /> : <div />}
          <Button mt="xl" variant="light" onClick={() => run(saveCredit.mutateAsync({ kind: draft.kind, body: creditBody() }))}>Enregistrer</Button>
        </SimpleGrid>)}
      {c.notes.map((n) => <Text key={n} size="xs" c="dimmed" mt={4}>{n}</Text>)}
      {error && <Alert color="brique" mt="sm">{error}</Alert>}
    </Paper>
  );
}
