// Choix d'une ou plusieurs lignes de relevé pour régler (ou encaisser) une facture : cases à cocher,
// total sélectionné face au restant, refus d'un total supérieur au restant. Une facture peut ainsi être
// réglée en plusieurs fois (fiche achat, encaissement d'une vente).
import type { ReactNode } from "react";
import { Checkbox, Group, Table, Text } from "@mantine/core";
import { MoneyText } from "../Money";
import { formatDate } from "../../lib/format";

export type PickableTransaction = {
  id: number;
  date: string;
  label: string;
  account: string;
  amount_cents: number;
  badges?: ReactNode;
};

export function selectedTotal(rows: PickableTransaction[], selected: number[]): number {
  return rows.filter((r) => selected.includes(r.id)).reduce((sum, r) => sum + Math.abs(r.amount_cents), 0);
}

export function TransactionPicker({ rows, selected, onChange, remainingCents, disabled = false }: {
  rows: PickableTransaction[];
  selected: number[];
  onChange: (ids: number[]) => void;
  remainingCents: number;
  disabled?: boolean;
}) {
  const total = selectedTotal(rows, selected);
  const over = total > remainingCents;
  const toggle = (id: number, on: boolean) => onChange(on ? [...selected, id] : selected.filter((i) => i !== id));
  return (
    <>
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th w={30} /><Table.Th>Date</Table.Th><Table.Th>Libellé</Table.Th>
            <Table.Th ta="right">Montant</Table.Th><Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((r) => {
            const checked = selected.includes(r.id);
            return (
              <Table.Tr key={r.id} bg={checked ? "var(--lv-surface-sunken)" : undefined}>
                <Table.Td>
                  <Checkbox checked={checked} disabled={disabled} aria-label={`${formatDate(r.date)} ${r.label}`}
                    onChange={(e) => toggle(r.id, e.currentTarget.checked)} />
                </Table.Td>
                <Table.Td className="lv-num">{formatDate(r.date)}</Table.Td>
                <Table.Td><Text size="sm">{r.label}</Text><Text size="xs" c="dimmed">{r.account}</Text></Table.Td>
                <Table.Td ta="right"><MoneyText cents={r.amount_cents} size="sm" /></Table.Td>
                <Table.Td><Group gap={4} wrap="nowrap">{r.badges}</Group></Table.Td>
              </Table.Tr>
            );
          })}
        </Table.Tbody>
      </Table>
      <Group justify="flex-end" gap="lg" mt={4} aria-live="polite">
        <Text size="sm">Sélection ({selected.length}) : <MoneyText cents={total} size="sm" fw={600} /></Text>
        <Text size="sm">Restant : <MoneyText cents={remainingCents} size="sm" fw={600} /></Text>
      </Group>
      {over && <Text size="sm" c="var(--lv-brique)" ta="right">La sélection dépasse le restant : retirez une ligne.</Text>}
    </>
  );
}
