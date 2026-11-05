// Cotisations MSA › appels (lot AG7.c, claudedocs/design_msa.md § 5) : registre des appels par exploitant et par année
// de cotisation, détail (cotisations, CSG déductible, CSG non déductible et CRDS, tiers) saisi ou estimé, paiement
// rapproché d'un débit bancaire, mensualités proposées, rappels de modulation.
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { Alert, Badge, Button, Group, NumberInput, Paper, Select, Table, Text, TextInput, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { MoneyInput, MoneyText } from "../../components/Money";

type Option = { value: string; label: string };
interface Payment { id: number; date: string; label: string; amount_cents: number }
export interface MsaCallRow {
  id: number; person_id: number; year: number; kind: string; kind_label: string; due_on: string; amount_cents: number;
  base_cents: number | null; contributions_cents: number | null; csg_deductible_cents: number | null;
  csg_crds_non_deductible_cents: number | null; third_party_cents: number | null; estimated: boolean; note: string | null;
  payment: Payment | null; proposal: { available: boolean; reason?: string; basis?: string } | null;
}
export interface MsaCallsView {
  year: number; warnings: string[]; monthly: boolean; kinds: Option[];
  people: { person: { id: number; name: string }; calls: MsaCallRow[]; retained_base_cents: number | null; retained_base_label: string;
    totals: { amount_cents: number; paid_cents: number; contributions_cents: number; csg_deductible_cents: number; csg_crds_non_deductible_cents: number } }[];
}

const money = (v: number | null) => (v === null ? "—" : <MoneyText cents={v} />);
const day = (iso: string) => new Date(iso).toLocaleDateString("fr-FR");

export function MsaCallsPanel({ defaultYear, editable }: { defaultYear: number; editable: boolean }) {
  const [year, setYear] = useState(defaultYear);
  const { data } = useQuery({ queryKey: ["msa", "calls", year], queryFn: () => api.get<{ item: MsaCallsView }>(`/api/v1/msa/calls?year=${year}`) });
  const [draft, setDraft] = useState<{ person: string | null; kind: string; due: string; amount: number | null; base: number | null;
    contributions: number | null; csgD: number | null; csgN: number | null }>({ person: null, kind: "first", due: "", amount: null, base: null, contributions: null, csgD: null, csgN: null });
  const [picking, setPicking] = useState<number | null>(null);
  // Lot AG9b.c : appel proposé par l'assistant (?proposal_id=) → formulaire prérempli, enregistré par l'utilisateur.
  const [search] = useSearchParams();
  const proposalId = Number(search.get("proposal_id")) || null;
  const { data: proposal } = useQuery({ queryKey: ["assistant", "proposal", proposalId], enabled: proposalId !== null,
    queryFn: () => api.get<{ item: { id: number; kind: string; status: string; payload: Record<string, unknown> } }>(`/api/v1/assistant/proposals/${proposalId}`) });
  useEffect(() => {
    const p = proposal?.item;
    if (!p || p.kind !== "msa_call" || p.status !== "open") return;
    const cents = (v: unknown) => (typeof v === "number" ? v : null);
    setYear(Number(p.payload.year) || year);
    setDraft((d) => ({ ...d, person: String(p.payload.person_id), kind: String(p.payload.kind), due: String(p.payload.due_on),
      amount: cents(p.payload.amount_cents), csgD: cents(p.payload.csg_deductible_cents), csgN: cents(p.payload.csg_crds_non_deductible_cents) }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [proposal]);
  const [error, setError] = useState<string | null>(null);
  const opts = { invalidate: [["msa"]] };
  const create = useAction((b: object) => api.post<{ notices: Notice[] }>("/api/v1/msa/calls", b), opts);
  const monthly = useAction((b: object) => api.post<{ notices: Notice[] }>("/api/v1/msa/calls/monthly", b), opts);
  const estimate = useAction((id: number) => api.post<{ notices: Notice[] }>(`/api/v1/msa/calls/${id}/estimate`, {}), opts);
  const remove = useAction((id: number) => api.delete<{ notices: Notice[] }>(`/api/v1/msa/calls/${id}`), opts);
  const pay = useAction(({ id, tx }: { id: number; tx: number | null }) => api.put<{ notices: Notice[] }>(`/api/v1/msa/calls/${id}/payment`, { bank_transaction_id: tx }), opts);
  const { data: cands } = useQuery({ queryKey: ["msa", "candidates", picking], enabled: picking !== null,
    queryFn: () => api.get<{ items: (Payment & { amount_matches: boolean; payee_matches: boolean })[] }>(`/api/v1/msa/calls/${picking}/candidates`) });
  if (!data?.item) return null;
  const v = data.item;
  const run = (x: Promise<unknown>, after?: () => void) => { setError(null); x.then(after, (e) => setError(e instanceof ApiError ? e.message : "Action impossible.")); };
  const personId = draft.person ?? (v.people[0] ? String(v.people[0].person.id) : null);
  return (
    <Paper withBorder p="md" mt="lg">
      <Group justify="space-between" mb="xs">
        <Title order={4}>Appels de cotisations</Title>
        <NumberInput aria-label="Année de cotisation" w={110} min={2000} max={2100} value={year} onChange={(x) => typeof x === "number" && setYear(x)} />
      </Group>
      {v.warnings.map((w) => <Alert key={w} color="paille" mb="xs">{w}</Alert>)}
      {v.people.map((p) => (
        <div key={p.person.id}>
          <Group gap="xs" mt="sm">
            <Text fw={600}>{p.person.name}</Text>
            <Text size="xs" c="dimmed">Assiette {year} : {p.retained_base_cents === null ? p.retained_base_label : <>{(p.retained_base_cents / 100).toLocaleString("fr-FR")} € ({p.retained_base_label})</>}</Text>
            {editable && v.monthly && !p.calls.some((c) => c.kind === "monthly") && (
              <Button size="compact-xs" variant="light" onClick={() => run(monthly.mutateAsync({ person_id: p.person.id, year }))}>Proposer les mensualités</Button>)}
          </Group>
          <Table>
            <Table.Thead><Table.Tr><Table.Th>Appel</Table.Th><Table.Th>Exigible le</Table.Th><Table.Th ta="right">Montant</Table.Th>
              <Table.Th ta="right">Cotisations</Table.Th><Table.Th ta="right">CSG déductible</Table.Th><Table.Th ta="right">CSG non déd. + CRDS</Table.Th>
              <Table.Th>Paiement</Table.Th><Table.Th /></Table.Tr></Table.Thead>
            <Table.Tbody>
              {p.calls.map((c) => (
                <Table.Tr key={c.id}>
                  <Table.Td><Text size="sm">{c.kind_label}</Text>{c.estimated && <Badge size="xs" color="gray">estimé</Badge>}
                    {c.note && <Text size="xs" c="dimmed">{c.note}</Text>}</Table.Td>
                  <Table.Td>{day(c.due_on)}</Table.Td>
                  <Table.Td ta="right"><MoneyText cents={c.amount_cents} /></Table.Td>
                  <Table.Td ta="right">{money(c.contributions_cents)}</Table.Td>
                  <Table.Td ta="right">{money(c.csg_deductible_cents)}</Table.Td>
                  <Table.Td ta="right">{money(c.csg_crds_non_deductible_cents)}
                    {c.proposal && (c.proposal.available
                      ? editable && <Button size="compact-xs" variant="subtle" title={c.proposal.basis} onClick={() => run(estimate.mutateAsync(c.id))}>Estimer</Button>
                      : <Text size="xs" c="dimmed">{c.proposal.reason}</Text>)}</Table.Td>
                  <Table.Td>{c.payment ? <Group gap={4}><Text size="xs">{day(c.payment.date)} · {c.payment.label}</Text>
                    {editable && <Button size="compact-xs" variant="subtle" onClick={() => run(pay.mutateAsync({ id: c.id, tx: null }))}>Détacher</Button>}</Group>
                    : editable && (picking === c.id
                      ? <Select size="xs" w={260} placeholder={cands?.items.length ? "Débit à rattacher" : "Aucun débit proche"}
                          data={(cands?.items ?? []).map((t) => ({ value: String(t.id), label: `${day(t.date)} · ${t.label} · ${(-t.amount_cents / 100).toLocaleString("fr-FR")} €${t.amount_matches ? " ✓" : ""}` }))}
                          onChange={(x) => x && run(pay.mutateAsync({ id: c.id, tx: Number(x) }), () => setPicking(null))} />
                      : <Button size="compact-xs" variant="subtle" onClick={() => setPicking(c.id)}>Rattacher</Button>)}</Table.Td>
                  <Table.Td>{editable && <Button size="compact-xs" variant="subtle" color="brique" onClick={() => run(remove.mutateAsync(c.id))}>Supprimer</Button>}</Table.Td>
                </Table.Tr>))}
              {p.calls.length > 0 && (
                <Table.Tr><Table.Td fw={600}>Total {year}</Table.Td><Table.Td /><Table.Td ta="right"><MoneyText cents={p.totals.amount_cents} fw={600} /></Table.Td>
                  <Table.Td ta="right"><MoneyText cents={p.totals.contributions_cents} /></Table.Td><Table.Td ta="right"><MoneyText cents={p.totals.csg_deductible_cents} /></Table.Td>
                  <Table.Td ta="right"><MoneyText cents={p.totals.csg_crds_non_deductible_cents} /></Table.Td>
                  <Table.Td><Text size="xs">payé <MoneyText cents={p.totals.paid_cents} /></Text></Table.Td><Table.Td /></Table.Tr>)}
            </Table.Tbody>
          </Table>
        </div>))}
      {editable && v.people.length > 0 && (
        <Group align="end" gap="xs" mt="sm">
          {v.people.length > 1 && <Select label="Exploitant" w={180} data={v.people.map((p) => ({ value: String(p.person.id), label: p.person.name }))}
            value={personId} allowDeselect={false} onChange={(x) => setDraft({ ...draft, person: x })} />}
          <Select label="Appel" w={190} data={v.kinds} value={draft.kind} allowDeselect={false} onChange={(x) => setDraft({ ...draft, kind: x ?? "first" })} />
          <TextInput label="Exigible le" type="date" w={150} value={draft.due} onChange={(e) => setDraft({ ...draft, due: e.currentTarget.value })} />
          <MoneyInput label="Montant" w={120} value={draft.amount} onChange={(x) => setDraft({ ...draft, amount: x })} />
          <MoneyInput label="Assiette de l'avis" w={130} value={draft.base} onChange={(x) => setDraft({ ...draft, base: x })} />
          <MoneyInput label="CSG déductible" w={120} value={draft.csgD} onChange={(x) => setDraft({ ...draft, csgD: x })} />
          <MoneyInput label="CSG non déd. + CRDS" w={140} value={draft.csgN} onChange={(x) => setDraft({ ...draft, csgN: x })} />
          <Button variant="light" loading={create.isPending} disabled={!draft.due || draft.amount === null}
            onClick={() => run(create.mutateAsync({ person_id: Number(personId), year, kind: draft.kind, due_on: draft.due, amount_cents: draft.amount,
              base_cents: draft.base, ...(draft.csgD !== null || draft.csgN !== null ? { csg_deductible_cents: draft.csgD ?? 0, csg_crds_non_deductible_cents: draft.csgN ?? 0 } : {}) }),
              () => {
                setDraft({ ...draft, due: "", amount: null, base: null, csgD: null, csgN: null });
                if (proposal?.item.status === "open") void api.patch(`/api/v1/assistant/proposals/${proposal.item.id}`, { status: "accepted" }).catch(() => undefined);
              })}>Enregistrer l'appel</Button>
        </Group>)}
      {error && <Alert color="brique" mt="sm">{error}</Alert>}
      <Text size="xs" c="dimmed" mt="xs">Détail laissé vide : « Estimer » répartit la CSG (6,8 % déductible, 2,4 % non déductible) et la CRDS (0,5 %) de l'assiette
        retenue au prorata des appels saisis. Modulation : demande à la caisse au moins 15 jours avant l'exigibilité.</Text>
    </Paper>
  );
}
