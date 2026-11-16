// Clôture › Inventaire (lot AG3.d, claudedocs/design_aides_pac.md § 6.1) : reprise des subventions d'investissement
// (D 139 / C 747 au dernier jour, au rythme de l'amortissement des biens financés, reste à la sortie du bien), reprise
// saisie avec un motif pour un bien non amortissable, et tableau des subventions (annexe).
import { useState } from "react";
import { Alert, Anchor, Button, Group, Paper, Select, Table, Text, TextInput } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { AppLink } from "../../app/navigation";
import { MoneyInput, MoneyText } from "../../components/Money";
import { StatusBadge } from "../../components/StatusBadge";

export interface GrantRelease {
  aid_id: number; aid_label: string; asset_id: number | null; asset_label: string | null;
  kind: "depreciation" | "disposal" | "manual"; amount_cents: number; dotation_cents: number | null; base_cents: number | null;
  posted: boolean; release_id: number | null; reason: string | null;
}
export interface GrantAnnexRow {
  aid_id: number; label: string; account_code: string; amount_cents: number; released_before_cents: number;
  released_cents: number; remaining_cents: number; assigned_cents: number; granted: boolean;
}
export interface GrantReleases { items: GrantRelease[]; annex: GrantAnnexRow[]; enabled: boolean; entry: { id: number; reference: string } | null }

const KIND_LABELS = { depreciation: "au rythme de l'amortissement", disposal: "sortie du bien", manual: "saisie" };

export function GrantReleasePanel({ fyId, editable }: { fyId: number; editable: boolean }) {
  const url = `/api/v1/fiscal-years/${fyId}/closing/aid-releases`;
  const { data } = useQuery({ queryKey: ["closing", fyId, "aid-releases"], queryFn: () => api.get<GrantReleases>(url) });
  const [manual, setManual] = useState<{ aid: string | null; amount: number | null; reason: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const opts = { invalidate: [["closing", fyId]] };
  const post = useAction(() => api.post<{ notices: Notice[] }>(url), opts);
  const cancel = useAction(() => api.delete<{ notices: Notice[] }>(url), opts);
  const add = useAction((b: object) => api.post<{ notices: Notice[] }>(`${url}/manual`, b), opts);
  const remove = useAction((id: number) => api.delete<{ notices: Notice[] }>(`${url}/manual/${id}`), opts);
  if (!data?.enabled || (!data.items.length && !data.annex.length)) return null;
  const run = (p: Promise<unknown>, after?: () => void) => {
    setError(null);
    p.then(after, (e) => setError(e instanceof ApiError ? e.message : "Action impossible."));
  };
  const total = data.items.reduce((s, r) => s + r.amount_cents, 0);
  return (
    <Paper withBorder p="sm">
      <Text fw={600} size="sm" mb={4}>Reprise des subventions d'investissement</Text>
      <Text size="xs" c="dimmed" mb="xs">D 139 / C 747 au dernier jour de l'exercice : montant affecté × dotation ÷ base amortissable
        de chaque bien financé ; à la sortie du bien, le reste. Non extournée.</Text>
      {data.items.length > 0 ? (
        <Table mb="xs">
          <Table.Thead><Table.Tr><Table.Th>Subvention</Table.Th><Table.Th>Bien</Table.Th><Table.Th>Calcul</Table.Th>
            <Table.Th ta="right">Reprise</Table.Th><Table.Th /></Table.Tr></Table.Thead>
          <Table.Tbody>
            {data.items.map((r, i) => (
              <Table.Tr key={`${r.aid_id}-${r.asset_id}-${r.kind}-${i}`}>
                <Table.Td>{r.aid_label}</Table.Td>
                <Table.Td>{r.asset_label ?? "—"}</Table.Td>
                <Table.Td><Text size="xs">{KIND_LABELS[r.kind]}{r.dotation_cents !== null && r.base_cents !== null && (
                  <> : dotation <MoneyText cents={r.dotation_cents} /> / base <MoneyText cents={r.base_cents} /></>)}</Text>
                  {r.reason && <Text size="xs" c="dimmed">{r.reason}</Text>}</Table.Td>
                <Table.Td ta="right"><MoneyText cents={r.amount_cents} /></Table.Td>
                <Table.Td ta="right">{r.posted ? <StatusBadge tone="ok">passée</StatusBadge>
                  : editable && r.kind === "manual" && r.release_id && (
                    <Button size="compact-sm" variant="subtle" color="brique" onClick={() => run(remove.mutateAsync(r.release_id!))}>Supprimer</Button>)}</Table.Td>
              </Table.Tr>))}
          </Table.Tbody>
        </Table>) : <Text size="sm" c="dimmed" mb="xs">Aucune reprise calculée pour l'exercice.</Text>}
      {data.entry && <Text size="sm" mb="xs">Écriture <Anchor component={AppLink} href={`/entries/${data.entry.id}`}>{data.entry.reference}</Anchor>.</Text>}
      {editable && (
        <Group gap="xs" mb="xs">
          <Button size="xs" loading={post.isPending} disabled={!total} onClick={() => run(post.mutateAsync(undefined))}>
            {data.entry ? "Repasser la reprise" : "Passer la reprise"}</Button>
          {data.entry && <Button size="xs" variant="subtle" color="brique" onClick={() => run(cancel.mutateAsync(undefined))}>Annuler l'écriture</Button>}
          {!manual && <Button size="xs" variant="default" onClick={() => setManual({ aid: null, amount: null, reason: "" })}>Reprise saisie…</Button>}
        </Group>)}
      {manual && (
        <Group align="end" gap="xs" mb="xs">
          <Select label="Subvention" w={260} data={data.annex.map((a) => ({ value: String(a.aid_id), label: a.label }))}
            value={manual.aid} onChange={(v) => setManual({ ...manual, aid: v })} />
          <MoneyInput label="Montant" w={130} value={manual.amount} onChange={(v) => setManual({ ...manual, amount: v })} />
          <TextInput label="Motif" w={260} value={manual.reason} onChange={(e) => setManual({ ...manual, reason: e.currentTarget.value })} />
          <Button disabled={!manual.aid || !manual.amount || manual.reason.trim().length < 5} loading={add.isPending}
            onClick={() => run(add.mutateAsync({ aid_id: Number(manual.aid), amount_cents: manual.amount, reason: manual.reason }), () => setManual(null))}>Ajouter</Button>
          <Button variant="default" onClick={() => setManual(null)}>Annuler</Button>
        </Group>)}
      {error && <Alert color="brique" mb="xs">{error}</Alert>}
      {data.annex.length > 0 && (
        <>
          <Text size="sm" fw={600} mt="sm">Subventions d'investissement (annexe)</Text>
          <Table>
            <Table.Thead><Table.Tr><Table.Th>Subvention</Table.Th><Table.Th ta="right">Montant</Table.Th><Table.Th ta="right">Reprises antérieures</Table.Th>
              <Table.Th ta="right">Reprise de l'exercice</Table.Th><Table.Th ta="right">Reste (131 − 139)</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {data.annex.map((a) => (
                <Table.Tr key={a.aid_id}>
                  <Table.Td>{a.label} <Text span size="xs" c="dimmed">{a.account_code}</Text>
                    {a.assigned_cents < a.amount_cents && <Text size="xs" c="var(--lv-paille-ink)">non affecté : <MoneyText cents={a.amount_cents - a.assigned_cents} /></Text>}</Table.Td>
                  <Table.Td ta="right"><MoneyText cents={a.amount_cents} /></Table.Td>
                  <Table.Td ta="right"><MoneyText cents={a.released_before_cents} /></Table.Td>
                  <Table.Td ta="right"><MoneyText cents={a.released_cents} /></Table.Td>
                  <Table.Td ta="right"><MoneyText cents={a.remaining_cents} /></Table.Td>
                </Table.Tr>))}
            </Table.Tbody>
          </Table>
        </>)}
    </Paper>
  );
}
