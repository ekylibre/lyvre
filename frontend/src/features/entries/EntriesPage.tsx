// Compta › Écritures : liste paginée côté serveur (exercice, journal, mois, recherche, tri).
import { Anchor, Button, Group, Select, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FilterBar, SearchInput, useUrlParams } from "../../components/FilterBar";
import { MoneyText } from "../../components/Money";
import { MonthSelect, type MonthOption } from "../../components/MonthSelect";
import { PageHeader } from "../../components/PageHeader";
import { Can } from "../../components/Can";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";

export const ENTRIES_KEY = ["entries"];

interface EntryRow {
  id: number; reference: string | null; entry_date: string; journal: string; description: string;
  total_debit_cents: number; is_balanced: boolean; source: string;
}
interface ListResponse {
  items: EntryRow[]; total: number; page: number; per_page: number;
  meta: { fy_id: number | null; fiscal_years: { value: string; label: string }[];
    journals: { value: string; label: string }[]; months: MonthOption[] };
}

const PER_PAGE = 50;

const COLUMNS: GridColumn<EntryRow>[] = [
  { accessor: "entry_date", title: "Date", sortable: true, hideable: false, render: (e) => <span className="lv-num">{formatDate(e.entry_date)}</span> },
  { accessor: "reference", title: "Référence", hideable: false,
    render: (e) => <Anchor component={AppLink} href={`/entries/${e.id}`} className="lv-num">{e.reference ?? `#${e.id}`}</Anchor> },
  { accessor: "journal", title: "Journal", render: (e) => <span className="lv-num">{e.journal}</span> },
  { accessor: "description", title: "Description", render: (e) => <Text size="sm" lineClamp={1}>{e.description}</Text> },
  { accessor: "source", title: "Origine", render: (e) => <Text size="sm" c="dimmed">{e.source === "MANUAL" ? "Saisie" : e.source}</Text> },
  { accessor: "total_debit_cents", title: "Montant", textAlign: "right", render: (e) => <MoneyText cents={e.total_debit_cents} /> },
  { accessor: "is_balanced", title: "Statut",
    render: (e) => e.is_balanced ? <StatusBadge tone="ok">Équilibrée</StatusBadge> : <StatusBadge tone="gap">Écart</StatusBadge> },
];

export default function EntriesPage() {
  const [params, setParams] = useUrlParams({ fy_id: "", journal_id: "", month: "", q: "", sort: "desc", page: "1" });
  const query = new URLSearchParams(Object.entries({ ...params, per_page: String(PER_PAGE) }).filter(([, v]) => v)).toString();
  const { data, isFetching } = useQuery({
    queryKey: [...ENTRIES_KEY, "list", query], placeholderData: (prev) => prev,
    queryFn: () => api.get<ListResponse>(`/api/v1/entries?${query}`),
  });
  const meta = data?.meta;
  const fyValue = params.fy_id || (meta?.fy_id ? String(meta.fy_id) : null);
  return (
    <>
      <PageHeader title="Écritures" description="Les écritures de l'exercice, de la plus récente à la plus ancienne."
        actions={<Can><Button component={AppLink} href="/entries/new">Saisir une écriture</Button></Can>} />
      <FilterBar>
        <Select label="Exercice" data={meta?.fiscal_years ?? []} value={fyValue} w={160} allowDeselect={false}
          onChange={(v) => setParams({ fy_id: v ?? "", month: "" })} />
        <Select label="Journal" placeholder="Tous" clearable data={meta?.journals ?? []} w={220}
          value={params.journal_id || null} onChange={(v) => setParams({ journal_id: v ?? "" })} />
        <MonthSelect value={params.month} onChange={(month) => setParams({ month })} options={meta?.months} />
        <SearchInput value={params.q} onChange={(q) => setParams({ q })} placeholder="Référence ou description…" />
      </FilterBar>
      <DataGrid id="entries" records={data?.items} columns={COLUMNS} fetching={isFetching}
        sort={{ column: "entry_date", direction: params.sort === "asc" ? "asc" : "desc" }}
        onSortChange={(s) => setParams({ sort: s.direction })}
        pagination={{ page: Number(params.page) || 1, perPage: PER_PAGE, total: data?.total ?? 0,
          onPageChange: (page) => setParams({ page: String(page) }) }}
        emptyText="Aucune écriture pour ces critères." />
      <Group mt="xs"><Text size="sm" c="dimmed">{data?.total ?? 0} écriture(s)</Text></Group>
    </>
  );
}
