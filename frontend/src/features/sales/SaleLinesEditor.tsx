// Lignes d'une facture de vente : produit du catalogue (remplit libellé, prix, TVA, compte, unité),
// désignation et description, quantité, unité, prix unitaire HT, remise, TVA, compte de vente,
// projet. HT de la ligne et totaux estimés à la saisie (le serveur arrondit la TVA par taux).
import { ActionIcon, Autocomplete, Button, Group, Select, Stack, Table, Text, TextInput, Textarea } from "@mantine/core";
import { Plus, X } from "lucide-react";
import { MoneyText } from "../../components/Money";
import type { Option } from "../purchases/types";
import { EMPTY_SALE_LINE, estimate, fromProduct, lineUntaxed, type SaleLineRow, type SaleProductOption } from "./types";

export function SaleLinesEditor({ rows, onChange, products, accounts, defaultAccount, units, projects, exempt }: {
  rows: SaleLineRow[]; onChange: (rows: SaleLineRow[]) => void; products: SaleProductOption[]; accounts: Option[];
  defaultAccount: string; units: string[]; projects: Option[]; exempt: boolean;
}) {
  const set = (index: number, patch: Partial<SaleLineRow>) => onChange(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  const pick = (index: number, id: string | null) =>
    onChange(rows.map((row, i) => (i === index ? fromProduct(row, products.find((p) => p.value === id), defaultAccount) : row)));
  const totals = estimate(rows, exempt);
  const n = (index: number) => ` (ligne ${index + 1})`;
  const numeric = { classNames: { input: "lv-num" }, styles: { input: { textAlign: "right" as const } }, inputMode: "decimal" as const };
  return (
    <Stack gap="xs">
      <Table.ScrollContainer minWidth={980}>
        <Table verticalSpacing={4}>
          <Table.Thead>
            <Table.Tr><Table.Th>Produit / désignation</Table.Th><Table.Th ta="right">Qté</Table.Th><Table.Th>Unité</Table.Th>
              <Table.Th ta="right">PU HT</Table.Th><Table.Th ta="right">Remise %</Table.Th>
              {!exempt && <Table.Th ta="right">TVA %</Table.Th>}<Table.Th>Compte</Table.Th>
              {projects.length > 0 && <Table.Th>Projet</Table.Th>}<Table.Th ta="right">HT</Table.Th><Table.Th /></Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((row, index) => (
              <Table.Tr key={index} style={{ verticalAlign: "top" }}>
                <Table.Td miw={240}>
                  <Stack gap={4}>
                    <Select aria-label={`Produit${n(index)}`} data={products} value={row.product_id || null} searchable clearable
                      placeholder="Produit du catalogue (facultatif)" onChange={(id) => pick(index, id)} />
                    <TextInput aria-label={`Désignation${n(index)}`} placeholder="Désignation" value={row.label}
                      onChange={(e) => set(index, { label: e.currentTarget.value })} />
                    <Textarea aria-label={`Description${n(index)}`} placeholder="Description (facultative)" autosize minRows={1}
                      value={row.description} onChange={(e) => set(index, { description: e.currentTarget.value })} />
                  </Stack>
                </Table.Td>
                <Table.Td><TextInput aria-label={`Quantité${n(index)}`} w={70} value={row.quantity} {...numeric}
                  onChange={(e) => set(index, { quantity: e.currentTarget.value })} /></Table.Td>
                <Table.Td><Autocomplete aria-label={`Unité${n(index)}`} w={90} data={units} value={row.unit}
                  onChange={(v) => set(index, { unit: v })} /></Table.Td>
                <Table.Td><TextInput aria-label={`Prix unitaire HT${n(index)}`} w={100} value={row.unit_price} {...numeric}
                  onChange={(e) => set(index, { unit_price: e.currentTarget.value })} /></Table.Td>
                <Table.Td><TextInput aria-label={`Remise${n(index)}`} w={70} value={row.discount} placeholder="0" {...numeric}
                  onChange={(e) => set(index, { discount: e.currentTarget.value })} /></Table.Td>
                {!exempt && <Table.Td><TextInput aria-label={`Taux de TVA${n(index)}`} w={70} value={row.vat_rate} placeholder="20" {...numeric}
                  onChange={(e) => set(index, { vat_rate: e.currentTarget.value })} /></Table.Td>}
                <Table.Td><Select aria-label={`Compte de vente${n(index)}`} w={150} data={accounts} value={row.account_code || null}
                  searchable placeholder={defaultAccount || "7…"} onChange={(v) => set(index, { account_code: v ?? "" })} /></Table.Td>
                {projects.length > 0 && <Table.Td><Select aria-label={`Projet${n(index)}`} data={projects} value={row.project_id || null}
                  clearable searchable placeholder="—" w={140} onChange={(v) => set(index, { project_id: v ?? "" })} /></Table.Td>}
                <Table.Td ta="right" pt={10}><MoneyText cents={lineUntaxed(row)} size="sm" /></Table.Td>
                <Table.Td><ActionIcon variant="subtle" color="red" aria-label={`Supprimer la ligne ${index + 1}`} mt={6}
                  onClick={() => onChange(rows.length > 1 ? rows.filter((_, i) => i !== index) : [EMPTY_SALE_LINE])}><X size={16} /></ActionIcon></Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      <Group justify="space-between" align="flex-start">
        <Button variant="default" size="compact-md" leftSection={<Plus size={14} />}
          onClick={() => onChange([...rows, { ...EMPTY_SALE_LINE, account_code: defaultAccount }])}>Ajouter une ligne</Button>
        <Stack gap={2} align="flex-end" aria-label="Totaux estimés">
          <Text size="sm">Total HT <MoneyText cents={totals.untaxed} size="sm" /></Text>
          {!exempt && <Text size="sm">TVA <MoneyText cents={totals.tax} size="sm" /></Text>}
          <Text fw={700}>Total {exempt ? "" : "TTC "}<MoneyText cents={totals.total} fw={700} /></Text>
        </Stack>
      </Group>
    </Stack>
  );
}
