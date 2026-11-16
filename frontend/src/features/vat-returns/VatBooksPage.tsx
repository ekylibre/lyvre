// Compta › Déclarations de TVA › Livres (lot AG2.d) : livre des ventes et livre des achats de la période (par défaut
// la période annuelle de la CA12A), totaux, contrôle croisé avec la CA12A, exports XLSX et PDF.
import { Alert, Button, Center, Group, Loader, SegmentedControl, Table, Text } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useQuery } from "@tanstack/react-query";
import { Download, FileText } from "lucide-react";
import { api } from "../../api/client";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { DataGrid } from "../../components/DataGrid";
import { AppLink } from "../../app/navigation";
import { formatDate } from "../../lib/format";
import { VAT_RETURNS_KEY, type PurchasesBook, type SalesBook } from "./types";

function query(params: { period: string; start: string; end: string }) {
  if (params.start && params.end) return `start=${params.start}&end=${params.end}`;
  return params.period ? `period=${params.period}` : "";
}

function SalesView({ book }: { book: SalesBook }) {
  return (
    <>
      {book.control && (
        <Alert color={book.control.ok ? "lichen" : "brique"} mb="md"
          title={book.control.ok ? "Totaux égaux aux lignes 01 à 09 de la CA12A" : "Écart avec la CA12A"}>
          {book.control.ok ? (book.control.validated ? "CA12A validée." : "CA12A en projet.")
            : `Lignes ${book.control.lines.filter((l) => !l.ok).map((l) => l.line).join(", ")} : une pièce antérieure reprise, `
              + "une pièce déclarée sur une autre période ou une vente datée hors période explique l'écart."}
        </Alert>)}
      <Table mb="lg" maw={720}>
        <Table.Thead><Table.Tr><Table.Th>Ligne</Table.Th><Table.Th>Catégorie</Table.Th><Table.Th ta="right">Base HT</Table.Th>
          <Table.Th ta="right">TVA</Table.Th>{book.control && <Table.Th ta="right">CA12A (base / TVA)</Table.Th>}</Table.Tr></Table.Thead>
        <Table.Tbody>
          {book.totals.map((t) => {
            const check = book.control?.lines.find((l) => l.line === t.line);
            return (
              <Table.Tr key={t.line ?? "other"}>
                <Table.Td className="lv-num">{t.line ?? "—"}</Table.Td><Table.Td>{t.category}</Table.Td>
                <Table.Td ta="right"><MoneyText cents={t.base_cents} /></Table.Td>
                <Table.Td ta="right"><MoneyText cents={t.tax_cents} /></Table.Td>
                {book.control && <Table.Td ta="right" className="lv-num" c={check && !check.ok ? "var(--lv-brique)" : undefined}>
                  {check ? `${check.return_base} € / ${check.return_tax} €` : ""}</Table.Td>}
              </Table.Tr>);
          })}
        </Table.Tbody>
      </Table>
      <DataGrid id="vat-sales-book" records={book.items.map((i, n) => ({ ...i, key: `${i.entry_id}-${i.code}-${n}` }))}
        idAccessor="key" emptyText="Aucune vente codée sur la période." columns={[
          { accessor: "date", title: "Date", render: (i) => <span className="lv-num">{formatDate(i.date)}</span> },
          { accessor: "reference", title: "Pièce", render: (i) => <AppLink href={`/entries/${i.entry_id}`}>{i.reference ?? `n° ${i.entry_id}`}</AppLink> },
          { accessor: "label", title: "Libellé" },
          { accessor: "entity", title: "Client" },
          { accessor: "category", title: "Catégorie", render: (i) => <>{i.category} <Text span size="xs" c="dimmed">{i.code}</Text></> },
          { accessor: "base_cents", title: "Base HT", textAlign: "right", render: (i) => <MoneyText cents={i.base_cents} /> },
          { accessor: "tax_cents", title: "TVA", textAlign: "right", render: (i) => <MoneyText cents={i.tax_cents} /> },
        ]} />
    </>
  );
}

function PurchasesView({ book }: { book: PurchasesBook }) {
  const c = book.control;
  return (
    <>
      {c && (
        <Alert color={c.ok ? "lichen" : "brique"} mb="md"
          title={c.ok ? "TVA déductible égale à la CA12A" : "Écart de TVA déductible avec la CA12A"}>
          Livre : {c.book_total} € (immobilisations {c.book_assets} €, autres {c.book_other} €) ; CA12A, lignes
          17 + 18 − 14 : {c.return_17} + {c.return_18} − {c.return_14} = {c.return_total} €.
          {!c.ok && " Une TVA déductible sans code de TVA, une pièce antérieure reprise ou déclarée ailleurs explique l'écart."}
        </Alert>)}
      <Table mb="lg" maw={860}>
        <Table.Thead><Table.Tr><Table.Th>Nature</Table.Th><Table.Th ta="right">Montant HT</Table.Th>
          <Table.Th ta="right">TVA déductible</Table.Th><Table.Th ta="right">TVA autoliquidée</Table.Th>
          <Table.Th ta="right">HT sans TVA déductible</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>
          {book.totals.map((t) => (
            <Table.Tr key={t.group}><Table.Td>{t.label}</Table.Td>
              <Table.Td ta="right"><MoneyText cents={t.ht_cents} /></Table.Td>
              <Table.Td ta="right"><MoneyText cents={t.deductible_cents} /></Table.Td>
              <Table.Td ta="right"><MoneyText cents={t.reverse_charge_cents} /></Table.Td>
              <Table.Td ta="right"><MoneyText cents={t.non_deductible_ht_cents} /></Table.Td></Table.Tr>))}
        </Table.Tbody>
      </Table>
      <DataGrid id="vat-purchases-book" records={book.items.map((i) => ({ ...i, key: `${i.entry_id}-${i.group}` }))}
        idAccessor="key" emptyText="Aucun achat sur la période." columns={[
          { accessor: "date", title: "Date", render: (i) => <span className="lv-num">{formatDate(i.date)}</span> },
          { accessor: "reference", title: "Pièce", render: (i) => <AppLink href={`/entries/${i.entry_id}`}>{i.reference ?? `n° ${i.entry_id}`}</AppLink> },
          { accessor: "label", title: "Libellé" },
          { accessor: "entity", title: "Fournisseur" },
          { accessor: "group_label", title: "Nature" },
          { accessor: "ht_cents", title: "Montant HT", textAlign: "right", render: (i) => <MoneyText cents={i.ht_cents} /> },
          { accessor: "deductible_cents", title: "TVA déductible", textAlign: "right", render: (i) => i.non_deductible
            ? <Text size="sm" c="dimmed">non déductible</Text> : <MoneyText cents={i.deductible_cents} /> },
          { accessor: "reverse_charge_cents", title: "Autoliquidée", textAlign: "right",
            render: (i) => i.reverse_charge_cents ? <MoneyText cents={i.reverse_charge_cents} /> : "" },
        ]} />
    </>
  );
}

export default function VatBooksPage() {
  const [params, setParams] = useUrlParams({ book: "sales", period: "", start: "", end: "" });
  const qs = query(params);
  const kind = params.book === "purchases" ? "purchases" : "sales";
  const { data } = useQuery({ queryKey: [...VAT_RETURNS_KEY, "books", kind, qs],
    queryFn: () => api.get<SalesBook | PurchasesBook>(`/api/v1/vat-books/${kind}${qs ? `?${qs}` : ""}`) });
  const exportQs = data ? `start=${data.start}&end=${data.end}` : qs;
  return (
    <>
      <PageHeader title="Livres de TVA"
        description="Livre des ventes et livre des achats (y compris les achats sans TVA déductible), à conserver avec la déclaration annuelle."
        actions={<Button variant="default" component={AppLink} href="/vat-returns/">Déclarations de TVA</Button>} />
      <FilterBar>
        <SegmentedControl value={kind} onChange={(v) => setParams({ book: v })}
          data={[{ value: "sales", label: "Ventes" }, { value: "purchases", label: "Achats" }]} />
        <DateInput aria-label="Du" placeholder="Du" valueFormat="DD/MM/YYYY" w={140}
          value={data?.start ?? null} onChange={(v) => v && setParams({ start: v.slice(0, 10), end: data?.end ?? v.slice(0, 10), period: "" })} />
        <DateInput aria-label="Au" placeholder="Au" valueFormat="DD/MM/YYYY" w={140}
          value={data?.end ?? null} onChange={(v) => v && setParams({ end: v.slice(0, 10), start: data?.start ?? v.slice(0, 10), period: "" })} />
        <Group gap="xs" ml="auto">
          <Button size="xs" variant="light" component="a" href={`/vat-books/${kind}.xlsx?${exportQs}`}
            leftSection={<Download size={14} />}>XLSX</Button>
          <Button size="xs" variant="light" component="a" target="_blank" href={`/vat-books/${kind}.pdf?${exportQs}`}
            leftSection={<FileText size={14} />}>PDF</Button>
        </Group>
      </FilterBar>
      {!data ? <Center h={300}><Loader /></Center>
        : kind === "sales" ? <SalesView book={data as SalesBook} /> : <PurchasesView book={data as PurchasesBook} />}
    </>
  );
}
