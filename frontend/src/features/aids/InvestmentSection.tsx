// Fiche d'un dossier d'aide (lot AG3.d, claudedocs/design_aides_pac.md § 6) : subvention d'investissement — octroi
// D 441 / C 131 à la décision, immobilisations financées et montant affecté à chacune (base de la reprise 139 / 747).
import { useState } from "react";
import { ActionIcon, Alert, Anchor, Button, Group, Select, Stack, Table, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { ApiError, api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { AppLink } from "../../app/navigation";
import { MoneyInput, MoneyText } from "../../components/Money";
import { formatDate } from "../../lib/format";

export interface AidInvestment {
  amount_cents: number; released_cents: number;
  grant_entry: { id: number; reference: string; entry_date: string } | null;
  assets: { asset_id: number; label: string; amount_cents: number; method: string; status: string }[];
}

type Row = { asset_id: number | null; amount: number | null };

export function InvestmentSection({ aidId, investment, hasPayments, invalidate }: {
  aidId: number; investment: AidInvestment; hasPayments: boolean; invalidate: unknown[][];
}) {
  const can = useCan();
  const { data: assets } = useQuery({ queryKey: ["assets", "for-aids"], enabled: can.write,
    queryFn: () => api.get<{ items: { id: number; label: string; acquisition_cents: number }[] }>("/api/v1/assets") });
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const opts = { invalidate };
  const grant = useAction(() => api.post<{ notices: Notice[] }>(`/api/v1/aids/${aidId}/grant`), opts);
  const cancel = useAction(() => api.delete<{ notices: Notice[] }>(`/api/v1/aids/${aidId}/grant`), opts);
  const save = useAction((body: object) => api.put<{ notices: Notice[] }>(`/api/v1/aids/${aidId}/assets`, body), opts);
  const run = (p: Promise<unknown>, after?: () => void) => {
    setError(null);
    p.then(after, (e) => setError(e instanceof ApiError ? e.message : "Action impossible."));
  };
  const editing = rows ?? investment.assets.map((a) => ({ asset_id: a.asset_id, amount: a.amount_cents }));
  const total = editing.reduce((s, r) => s + (r.amount ?? 0), 0);
  const options = (assets?.items ?? []).map((a) => ({ value: String(a.id), label: a.label }));
  return (
    <Stack gap="xs">
      <Title order={5}>Subvention d'investissement</Title>
      <Text size="sm">Montant <MoneyText cents={investment.amount_cents} /> · repris <MoneyText cents={investment.released_cents} /></Text>
      {investment.grant_entry ? (
        <Group gap="xs">
          <Text size="sm">Octroi passé le {formatDate(investment.grant_entry.entry_date)} :{" "}
            <Anchor component={AppLink} href={`/entries/${investment.grant_entry.id}`}>{investment.grant_entry.reference}</Anchor> (D 441 / C 131)</Text>
          {can.write && !hasPayments && <Button size="compact-sm" variant="subtle" color="brique" onClick={() => run(cancel.mutateAsync(undefined))}>Annuler l'octroi</Button>}
        </Group>
      ) : (
        <Group gap="xs">
          <Text size="sm" c="dimmed">{hasPayments ? "Versements comptabilisés sans octroi (directement sur le compte de la subvention)."
            : "Octroi non comptabilisé : D 441 / C 131 à la date de la décision, avant le premier versement."}</Text>
          {can.write && !hasPayments && <Button size="compact-sm" variant="light" loading={grant.isPending}
            onClick={() => run(grant.mutateAsync(undefined))}>Passer l'octroi</Button>}
        </Group>)}
      <Text size="sm" fw={600}>Immobilisations financées</Text>
      <Table>
        <Table.Tbody>
          {editing.map((r, i) => (
            <Table.Tr key={i}>
              <Table.Td>{can.write ? (
                <Select aria-label={`Immobilisation ${i + 1}`} data={options} searchable value={r.asset_id ? String(r.asset_id) : null}
                  onChange={(v) => setRows(editing.map((x, j) => (j === i ? { ...x, asset_id: v ? Number(v) : null } : x)))} />)
                : investment.assets[i]?.label}</Table.Td>
              <Table.Td>{can.write ? <MoneyInput aria-label={`Montant affecté ${i + 1}`} w={140} value={r.amount}
                onChange={(v) => setRows(editing.map((x, j) => (j === i ? { ...x, amount: v } : x)))} />
                : <MoneyText cents={r.amount ?? 0} />}</Table.Td>
              <Table.Td>{can.write && <ActionIcon variant="subtle" aria-label="Retirer" onClick={() => setRows(editing.filter((_, j) => j !== i))}><X size={14} /></ActionIcon>}</Table.Td>
            </Table.Tr>))}
        </Table.Tbody>
      </Table>
      <Text size="xs" c="dimmed">Affecté <MoneyText cents={total} /> sur <MoneyText cents={investment.amount_cents} /> ; reprise au rythme
        de l'amortissement de chaque bien (terre : reprise saisie à la clôture).</Text>
      {can.write && (
        <Group gap="xs">
          <Button size="xs" variant="default" onClick={() => setRows([...editing, { asset_id: null, amount: null }])}>Ajouter une immobilisation</Button>
          {rows && <Button size="xs" loading={save.isPending} disabled={editing.some((r) => !r.asset_id || !r.amount)}
            onClick={() => run(save.mutateAsync({ assets: editing.map((r) => ({ asset_id: r.asset_id, amount_cents: r.amount })) }), () => setRows(null))}>
            Enregistrer les immobilisations</Button>}
        </Group>)}
      {error && <Alert color="brique">{error}</Alert>}
    </Stack>
  );
}
