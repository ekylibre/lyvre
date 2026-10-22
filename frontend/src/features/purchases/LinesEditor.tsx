// Éditeur des lignes d'une facture d'achat : produit, compte, libellé, projet (si l'instance en a),
// HT, taux, TVA ; TTC recalculé à la saisie et comparé au TTC attendu.
import { ActionIcon, Autocomplete, Button, Select, Table, Text, TextInput } from "@mantine/core";
import { Plus, X } from "lucide-react";
import { MoneyText } from "../../components/Money";
import { EMPTY_LINE, lineTotal, linesTotal, updateLine } from "./lines";
import type { LineRow, Option, ProductOption } from "./types";

export function LinesEditor({ rows, onChange, products, accounts, projects = [], expected, expectedLabel = "TTC" }: {
  rows: LineRow[]; onChange: (rows: LineRow[]) => void; products: ProductOption[]; accounts: Option[]; projects?: Option[];
  /** TTC attendu en centimes (null : inconnu). */
  expected: number | null; expectedLabel?: string;
}) {
  const set = (index: number, field: keyof LineRow, value: string) =>
    onChange(rows.map((row, i) => (i === index ? updateLine(row, field, value, products) : row)));
  const total = linesTotal(rows);
  const accountData = accounts.map((a) => ({ value: a.value, label: a.label }));
  const amount = (index: number, field: "untaxed" | "vat_rate" | "vat", label: string, width: number, placeholder?: string) => (
    <TextInput aria-label={`${label} (ligne ${index + 1})`} value={rows[index][field]} inputMode="decimal" w={width}
      placeholder={placeholder} classNames={{ input: "lv-num" }} styles={{ input: { textAlign: "right" } }}
      onChange={(e) => set(index, field, e.currentTarget.value)} />
  );
  return (
    <>
      <Table.ScrollContainer minWidth={820}>
        <Table verticalSpacing={4}>
          <Table.Thead>
            <Table.Tr><Table.Th>Produit</Table.Th><Table.Th>Compte</Table.Th><Table.Th>Libellé</Table.Th>
              {projects.length > 0 && <Table.Th>Projet</Table.Th>}
              <Table.Th ta="right">HT</Table.Th><Table.Th ta="right">Taux %</Table.Th><Table.Th ta="right">TVA</Table.Th>
              <Table.Th ta="right">TTC</Table.Th><Table.Th /></Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((row, index) => (
              <Table.Tr key={index}>
                <Table.Td><Select aria-label={`Produit (ligne ${index + 1})`} data={products} value={row.product_id || null} clearable searchable
                  placeholder="—" w={180} onChange={(v) => set(index, "product_id", v ?? "")} /></Table.Td>
                <Table.Td><Autocomplete aria-label={`Compte (ligne ${index + 1})`} data={accountData.map((a) => a.value)} value={row.account_code}
                  w={110} classNames={{ input: "lv-num" }} onChange={(v) => set(index, "account_code", v)}
                  renderOption={({ option }) => <Text size="sm">{accountData.find((a) => a.value === option.value)?.label}</Text>} /></Table.Td>
                <Table.Td><TextInput aria-label={`Libellé (ligne ${index + 1})`} value={row.label} miw={160}
                  onChange={(e) => set(index, "label", e.currentTarget.value)} /></Table.Td>
                {projects.length > 0 && <Table.Td><Select aria-label={`Projet (ligne ${index + 1})`} data={projects} value={row.project_id || null}
                  clearable searchable placeholder="—" w={150} onChange={(v) => set(index, "project_id", v ?? "")} /></Table.Td>}
                <Table.Td>{amount(index, "untaxed", "HT", 100)}</Table.Td>
                <Table.Td>{amount(index, "vat_rate", "Taux de TVA", 70, "?")}</Table.Td>
                <Table.Td>{amount(index, "vat", "TVA", 90)}</Table.Td>
                <Table.Td ta="right"><MoneyText cents={lineTotal(row)} size="sm" /></Table.Td>
                <Table.Td><ActionIcon variant="subtle" color="red" aria-label={`Supprimer la ligne ${index + 1}`}
                  onClick={() => onChange(rows.length > 1 ? rows.filter((_, i) => i !== index) : [EMPTY_LINE])}><X size={16} /></ActionIcon></Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
          <Table.Tfoot>
            <Table.Tr>
              <Table.Td colSpan={projects.length > 0 ? 7 : 6} ta="right"><Text fw={600} size="sm">Total des lignes / {expectedLabel}</Text></Table.Td>
              <Table.Td ta="right" style={{ whiteSpace: "nowrap" }}>
                <MoneyText cents={total} fw={600} size="sm" anomaly={expected !== null && total !== expected} />
                {" / "}{expected === null ? "—" : <MoneyText cents={expected} size="sm" />}
              </Table.Td>
              <Table.Td />
            </Table.Tr>
          </Table.Tfoot>
        </Table>
      </Table.ScrollContainer>
      <Button variant="default" size="compact-md" leftSection={<Plus size={14} />} onClick={() => onChange([...rows, EMPTY_LINE])}>
        Ajouter une ligne</Button>
    </>
  );
}
