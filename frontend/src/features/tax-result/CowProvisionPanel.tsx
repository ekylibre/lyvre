// Résultat fiscal › provision 73 A (lot AG6.d, claudedocs/design_fiscalite_ba.md § 6) : hausse de valeur des vaches
// laitières et allaitantes par catégorie (sans compensation), plafond par exploitant, minoration sans contrat
// pluriannuel (EGALIM), écriture gérée D 6873 / C 1483 et reprises D 1483 / C 7873 (sorties, 6e exercice).
import { useState } from "react";
import { Alert, Badge, Button, Checkbox, Group, Paper, Select, Table, Text, TextInput, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { MoneyText } from "../../components/Money";

export interface CowProvisionView {
  proposal: { eligible: boolean; reason: string | null; increase_cents: number; cap_cents: number; operators: number;
    egalim_contract: boolean | null; minoration_bp: number; amount_cents: number; heads: number; value_cents: number; warnings: string[];
    categories: { category: string; label: string; opening_cents: number | null; closing_cents: number; heads: number; increase_cents: number }[] };
  plan: { provision_id: number; origin: string; kind: string; heads?: number; amount_cents: number }[];
  register: { id: number; origin: string; amount_cents: number; heads: number; value_cents: number; remaining_cents: number;
    releases: { fiscal_year: string; kind: string; kind_label: string; heads: number | null; amount_cents: number; reason: string | null }[] }[];
  constituted: boolean; entry: { id: number; reference: string } | null;
}

const PLAN_LABELS: Record<string, string> = { exit: "sorties de vaches", sixth_year: "6e exercice : réintégration", exempt: "6e exercice : exonération" };

export function CowProvisionPanel({ fyId, editable }: { fyId: number; editable: boolean }) {
  const url = `/api/v1/fiscal-years/${fyId}/cow-provision`;
  const { data } = useQuery({ queryKey: ["tax-result", fyId, "cow"], queryFn: () => api.get<{ item: CowProvisionView }>(url) });
  const [constitute, setConstitute] = useState(true);
  const [waiver, setWaiver] = useState<{ provision: string | null; reason: string }>({ provision: null, reason: "" });
  const [error, setError] = useState<string | null>(null);
  const opts = { invalidate: [["tax-result"]] };
  const post = useAction((b: object) => api.post<{ notices: Notice[] }>(url, b), opts);
  const cancel = useAction(() => api.delete<{ notices: Notice[] }>(url), opts);
  const waive = useAction((b: object) => api.post<{ notices: Notice[] }>(`${url}/waivers`, b), opts);
  const egalim = useAction((v: boolean) => api.put<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fyId}/egalim`, { egalim_contract: v }), opts);
  if (!data?.item) return null;
  const d = data.item;
  const p = d.proposal;
  const hasHerd = p.heads > 0 || d.register.length > 0;
  if (!hasHerd && !p.categories.some((c) => c.opening_cents)) return null;
  const run = (x: Promise<unknown>, after?: () => void) => { setError(null); x.then(after, (e) => setError(e instanceof ApiError ? e.message : "Action impossible.")); };
  return (
    <Paper withBorder p="md" mt="lg">
      <Group justify="space-between" mb="xs">
        <Title order={4}>Provision pour augmentation du stock de vaches (art. 73 A)</Title>
        {d.entry && <Badge color="mousse">Écriture {d.entry.reference}</Badge>}
      </Group>
      {!p.eligible && p.reason && <Alert color="gray" mb="xs">{p.reason}</Alert>}
      {p.warnings.map((w) => <Alert key={w} color="paille" mb="xs">{w}</Alert>)}
      <Table mb="sm">
        <Table.Thead><Table.Tr><Table.Th>Catégorie</Table.Th><Table.Th ta="right">Ouverture</Table.Th><Table.Th ta="right">Clôture</Table.Th>
          <Table.Th ta="right">Têtes</Table.Th><Table.Th ta="right">Hausse retenue</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>
          {p.categories.map((c) => (
            <Table.Tr key={c.category}><Table.Td>{c.label}</Table.Td>
              <Table.Td ta="right">{c.opening_cents !== null ? <MoneyText cents={c.opening_cents} /> : "—"}</Table.Td>
              <Table.Td ta="right"><MoneyText cents={c.closing_cents} /></Table.Td>
              <Table.Td ta="right" className="lv-num">{c.heads}</Table.Td>
              <Table.Td ta="right"><MoneyText cents={c.increase_cents} /></Table.Td></Table.Tr>))}
        </Table.Tbody>
      </Table>
      <Text size="sm">
        Hausse sans compensation entre catégories <MoneyText cents={p.increase_cents} />, plafond <MoneyText cents={p.cap_cents} />
        {p.operators > 1 ? ` (${p.operators} exploitants)` : ""}{p.minoration_bp ? `, minoration de ${(p.minoration_bp / 100).toLocaleString("fr-FR")} % sans contrat pluriannuel` : ""} :
        provision possible <MoneyText cents={p.amount_cents} fw={600} />.
      </Text>
      {editable && p.eligible && (
        <Checkbox mt="xs" label="Contrat pluriannuel (EGALIM) en cours à la clôture : pas de minoration" checked={!!p.egalim_contract}
          onChange={(e) => run(egalim.mutateAsync(e.currentTarget.checked))} />)}

      {d.plan.length > 0 && (
        <>
          <Text fw={600} size="sm" mt="sm">Reprises de l'exercice</Text>
          {d.plan.map((r) => (
            <Text key={`${r.provision_id}-${r.kind}`} size="sm">Provision {r.origin} — {PLAN_LABELS[r.kind] ?? r.kind}
              {r.heads ? ` (${r.heads} têtes)` : ""} : <MoneyText cents={r.amount_cents} /></Text>))}
        </>)}

      {editable && !d.entry && (p.amount_cents > 0 || d.plan.length > 0) && (
        <Group gap="xs" mt="sm">
          {p.amount_cents > 0 && <Checkbox label="Constituer la provision de l'exercice (option)" checked={constitute} onChange={(e) => setConstitute(e.currentTarget.checked)} />}
          <Button size="sm" loading={post.isPending} onClick={() => run(post.mutateAsync({ constitute: constitute && p.amount_cents > 0 }))}>Passer l'écriture</Button>
        </Group>)}
      {editable && d.entry && (
        <Button mt="sm" size="sm" variant="default" color="brique" loading={cancel.isPending} onClick={() => run(cancel.mutateAsync())}>Annuler l'écriture</Button>)}

      {d.register.length > 0 && (
        <>
          <Text fw={600} size="sm" mt="md">Registre</Text>
          <Table>
            <Table.Thead><Table.Tr><Table.Th>Exercice</Table.Th><Table.Th ta="right">Dotation</Table.Th><Table.Th>Reprises</Table.Th><Table.Th ta="right">Reste</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {d.register.map((r) => (
                <Table.Tr key={r.id}><Table.Td>{r.origin}</Table.Td><Table.Td ta="right"><MoneyText cents={r.amount_cents} /></Table.Td>
                  <Table.Td>{r.releases.map((x, i) => (
                    <Text key={i} size="xs">{x.fiscal_year} · {x.kind_label}{x.heads ? ` (${x.heads} têtes)` : ""}{x.amount_cents ? <> : <MoneyText cents={x.amount_cents} /></> : ""}{x.reason ? ` — ${x.reason}` : ""}</Text>))}</Table.Td>
                  <Table.Td ta="right"><MoneyText cents={r.remaining_cents} /></Table.Td></Table.Tr>))}
            </Table.Tbody>
          </Table>
          {editable && !d.entry && (
            <Group align="end" gap="xs" mt="xs">
              <Select label="Sortie sans reprise" placeholder="provision" w={160} data={d.register.filter((r) => r.remaining_cents > 0).map((r) => ({ value: String(r.id), label: r.origin }))}
                value={waiver.provision} onChange={(v) => setWaiver({ ...waiver, provision: v })} />
              <TextInput label="Motif" w={300} placeholder="remplacement avant le dépôt, abattage administratif…" value={waiver.reason}
                onChange={(e) => setWaiver({ ...waiver, reason: e.currentTarget.value })} />
              <Button variant="light" disabled={!waiver.provision || waiver.reason.length < 5}
                onClick={() => run(waive.mutateAsync({ provision_id: Number(waiver.provision), reason: waiver.reason }), () => setWaiver({ provision: null, reason: "" }))}>Enregistrer</Button>
            </Group>)}
        </>)}
      {error && <Alert color="brique" mt="sm">{error}</Alert>}
    </Paper>
  );
}
