// Compta › Écritures : liste paginée côté serveur (exercice, journal, état, mois, recherche, tri) ;
// validation d'une sélection ou de tout jusqu'à une date (lot F1).
import { useState } from "react";
import { Alert, Anchor, Button, Group, Select, Text } from "@mantine/core";
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
import { useAction, type Notice } from "../../api/resources";
import { FormModal } from "../../components/FormModal";
import { ValidateUntilForm, ValidationRefusals, VALIDATION_KEY } from "./validation";

export const ENTRIES_KEY = ["entries"];

interface EntryRow {
  id: number; reference: string | null; entry_date: string; journal: string; description: string;
  total_debit_cents: number; is_balanced: boolean; source: string; validation_number: number | null;
}
interface ListResponse {
  items: EntryRow[]; total: number; page: number; per_page: number;
  meta: { fy_id: number | null; fiscal_years: { value: string; label: string }[];
    journals: { value: string; label: string }[]; months: MonthOption[];
    drafts: { drafts: number; old: number } | null; fiscal_year_open: boolean };
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
  { accessor: "validation_number", title: "État",
    render: (e) => !e.is_balanced ? <StatusBadge tone="gap">Écart</StatusBadge>
      : e.validation_number ? <span title="Validée : numéro définitif"><StatusBadge tone="ok">{`n° ${e.validation_number}`}</StatusBadge></span>
        : <StatusBadge tone="todo">Brouillard</StatusBadge> },
];

const STATES = [{ value: "draft", label: "Brouillard" }, { value: "validated", label: "Validées" }];

export default function EntriesPage() {
  const [params, setParams] = useUrlParams({ fy_id: "", journal_id: "", state: "", month: "", q: "", sort: "desc", page: "1" });
  const [selected, setSelected] = useState<EntryRow[]>([]);
  const [untilOpen, setUntilOpen] = useState(false);
  const validate = useAction((ids: number[]) => api.post<{ notices: Notice[] }>("/api/v1/entries/validation", { ids }),
    { invalidate: [ENTRIES_KEY, VALIDATION_KEY] });
  const query = new URLSearchParams(Object.entries({ ...params, per_page: String(PER_PAGE) }).filter(([, v]) => v)).toString();
  const { data, isFetching } = useQuery({
    queryKey: [...ENTRIES_KEY, "list", query], placeholderData: (prev) => prev,
    queryFn: () => api.get<ListResponse>(`/api/v1/entries?${query}`),
  });
  const meta = data?.meta;
  const fyValue = params.fy_id || (meta?.fy_id ? String(meta.fy_id) : null);
  return (
    <>
      <PageHeader title="Écritures" description="Les écritures de l'exercice, de la plus récente à la plus ancienne. Une écriture validée a son numéro définitif et ne se modifie plus."
        actions={<Can>
          {meta?.fiscal_year_open && <Button variant="default" onClick={() => setUntilOpen(true)}>Valider jusqu'au…</Button>}
          <Button component={AppLink} href="/entries/new">Saisir une écriture</Button></Can>} />
      {!!meta?.drafts?.old && <Alert color="paille" variant="light" mb="sm">{meta.drafts.old} écriture(s) en brouillard depuis plus de
        3 mois : validez-les une fois vérifiées.</Alert>}
      <ValidationRefusals error={validate.error} />
      <FilterBar>
        <Select label="Exercice" data={meta?.fiscal_years ?? []} value={fyValue} w={160} allowDeselect={false}
          onChange={(v) => setParams({ fy_id: v ?? "", month: "" })} />
        <Select label="Journal" placeholder="Tous" clearable data={meta?.journals ?? []} w={220}
          value={params.journal_id || null} onChange={(v) => setParams({ journal_id: v ?? "" })} />
        <Select label="État" placeholder="Tous" clearable data={STATES} w={140}
          value={params.state || null} onChange={(v) => setParams({ state: v ?? "" })} />
        <MonthSelect value={params.month} onChange={(month) => setParams({ month })} options={meta?.months} />
        <SearchInput value={params.q} onChange={(q) => setParams({ q })} placeholder="Référence ou description…" />
      </FilterBar>
      <DataGrid id="entries" records={data?.items} columns={COLUMNS} fetching={isFetching}
        sort={{ column: "entry_date", direction: params.sort === "asc" ? "asc" : "desc" }}
        onSortChange={(s) => setParams({ sort: s.direction })}
        pagination={{ page: Number(params.page) || 1, perPage: PER_PAGE, total: data?.total ?? 0,
          onPageChange: (page) => setParams({ page: String(page) }) }}
        selection={{ selected, onChange: setSelected, actions: (rows) => {
          const drafts = rows.filter((r) => !r.validation_number).map((r) => r.id);
          return drafts.length ? <Button size="compact-sm" loading={validate.isPending}
            onClick={() => validate.mutate(drafts, { onSuccess: () => setSelected([]) })}>{`Valider (${drafts.length})`}</Button> : null;
        } }}
        emptyText="Aucune écriture pour ces critères." />
      <FormModal opened={untilOpen} onClose={() => setUntilOpen(false)} title="Valider les écritures">
        {untilOpen && meta?.fy_id && <ValidateUntilForm fiscalYearId={meta.fy_id} invalidate={[ENTRIES_KEY]} onDone={() => setUntilOpen(false)} />}
      </FormModal>
      <Group mt="xs"><Text size="sm" c="dimmed">{data?.total ?? 0} écriture(s)</Text></Group>
    </>
  );
}
