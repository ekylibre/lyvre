// Banque › Transactions : rattacher un virement reçu à un ou plusieurs dossiers d'aide (lot AG3.b,
// claudedocs/design_aides_pac.md § 5). Proposé puis confirmé (AGD20 Q-P6) ; un virement libre est comptabilisé sur
// les comptes des dossiers s'il est entièrement ventilé, un virement déjà comptabilisé n'est jamais réécrit.
import { useState } from "react";
import { Alert, Button, Center, Checkbox, Group, Loader, Select, Stack, Table, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { FormModal } from "../../components/FormModal";
import { MoneyInput, MoneyText } from "../../components/Money";
import { formatDate } from "../../lib/format";
import { AIDS_KEY, type Aid } from "./AidsPage";

export interface AidCandidates {
  transaction: { id: number; label: string | null; counterparty: string | null; transaction_date: string; amount_cents: number;
    booked: boolean; booked_accounts: string[] };
  payer: string | null; allocated_cents: number; free_cents: number;
  items: { aid: Aid; payer_match: boolean; suggested_cents: number; already_linked: boolean }[];
}

const KINDS = [{ value: "advance", label: "Avance" }, { value: "balance", label: "Solde" },
  { value: "installment", label: "Fraction" }, { value: "other", label: "Autre" }];

function LinkForm({ txId, invalidate, onDone }: { txId: number; invalidate: unknown[][]; onDone: () => void }) {
  const { data } = useQuery({ queryKey: [...AIDS_KEY, "candidates", txId],
    queryFn: () => api.get<{ item: AidCandidates }>(`/api/v1/aids/candidates?bank_transaction_id=${txId}`) });
  const [rows, setRows] = useState<Record<number, { on: boolean; amount: number | null; kind: string }>>({});
  const [book, setBook] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const link = useAction((body: object) => api.post<{ notices: Notice[] }>("/api/v1/aids/link", body),
    { invalidate: [AIDS_KEY, ...invalidate] });
  if (!data) return <Center h={160}><Loader /></Center>;
  const c = data.item;
  const first = c.items.find((r) => r.payer_match && !r.already_linked && r.suggested_cents > 0);
  const rowOf = (aidId: number, suggested: number) => rows[aidId]
    ?? { on: aidId === first?.aid.id, amount: suggested, kind: first?.aid.id === aidId ? "advance" : "balance" };
  const picked = c.items.map((r) => ({ r, s: rowOf(r.aid.id, r.suggested_cents) })).filter((x) => x.s.on);
  const total = picked.reduce((sum, x) => sum + (x.s.amount ?? 0), 0);
  const canBook = !c.transaction.booked && c.allocated_cents === 0;
  const submit = () => {
    setError(null);
    link.mutateAsync({ bank_transaction_id: txId, book: canBook && book,
      allocations: picked.map((x) => ({ aid_id: x.r.aid.id, amount_cents: x.s.amount, kind: x.s.kind })) })
      .then(onDone, (e) => setError(e instanceof ApiError ? e.message : "Rattachement impossible."));
  };
  return (
    <form onSubmit={(e) => { e.preventDefault(); submit(); }}>
      <Stack>
        <Text size="sm">{formatDate(c.transaction.transaction_date)} — {c.transaction.label} — <MoneyText cents={c.transaction.amount_cents} />
          {c.payer && ` · payeur reconnu : ${c.payer}`}</Text>
        {c.allocated_cents > 0 && <Text size="sm" c="dimmed">Déjà rattaché : <MoneyText cents={c.allocated_cents} /> ; reste <MoneyText cents={c.free_cents} />.</Text>}
        {c.transaction.booked && (
          <Text size="sm" c="dimmed">Comptabilisé{c.transaction.booked_accounts.length > 0 && ` en ${c.transaction.booked_accounts.join(", ")}`} :
            le rattachement ne modifie pas l'écriture.</Text>)}
        {c.items.length === 0 ? <Text c="dimmed">Aucun dossier ouvert avec un reste à percevoir. Créez d'abord le dossier dans Compta › Aides et subventions.</Text> : (
          <Table>
            <Table.Thead><Table.Tr><Table.Th /><Table.Th>Dossier</Table.Th><Table.Th ta="right">Reste</Table.Th><Table.Th>Montant</Table.Th><Table.Th>Type</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {c.items.map(({ aid, suggested_cents, payer_match }) => {
                const s = rowOf(aid.id, suggested_cents);
                const set = (patch: Partial<typeof s>) => setRows((all) => ({ ...all, [aid.id]: { ...s, ...patch } }));
                return (
                  <Table.Tr key={aid.id}>
                    <Table.Td><Checkbox aria-label={`Rattacher à ${aid.label} ${aid.campaign}`} checked={s.on} onChange={(e) => set({ on: e.currentTarget.checked })} /></Table.Td>
                    <Table.Td>{aid.label} {aid.campaign} <Text span size="xs" c="dimmed">{aid.account.code}{!payer_match && aid.payer ? ` · ${aid.payer}` : ""}</Text></Table.Td>
                    <Table.Td ta="right"><MoneyText cents={aid.remaining_cents} /></Table.Td>
                    <Table.Td><MoneyInput aria-label={`Montant pour ${aid.label}`} w={130} disabled={!s.on} value={s.amount} onChange={(v) => set({ amount: v })} /></Table.Td>
                    <Table.Td><Select aria-label={`Type pour ${aid.label}`} w={120} data={KINDS} disabled={!s.on} value={s.kind} allowDeselect={false}
                      onChange={(v) => set({ kind: v ?? "other" })} /></Table.Td>
                  </Table.Tr>);
              })}
            </Table.Tbody>
          </Table>)}
        <Text size="sm">Ventilé : <MoneyText cents={total} /> sur <MoneyText cents={c.free_cents} />.</Text>
        {canBook && (
          <Checkbox checked={book} onChange={(e) => setBook(e.currentTarget.checked)} label="Comptabiliser le virement sur les comptes des dossiers"
            description={book && total !== c.free_cents ? "Ventilez la totalité du virement pour le comptabiliser." : undefined} />)}
        {error && <Alert color="brique">{error}</Alert>}
        <Group><Button type="submit" disabled={picked.length === 0 || total <= 0 || total > c.free_cents} loading={link.isPending}>Rattacher</Button></Group>
      </Stack>
    </form>
  );
}

export function LinkAidModal({ txId, invalidate = [], onClose }: { txId: number | null; invalidate?: unknown[][]; onClose: () => void }) {
  return (
    <FormModal opened={txId !== null} onClose={onClose} title="Rattacher à une aide" size="xl">
      {txId !== null && <LinkForm txId={txId} invalidate={invalidate} onDone={onClose} />}
    </FormModal>
  );
}
