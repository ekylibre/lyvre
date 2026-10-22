// Tableau des listes (F6) : tri, sélection et actions groupées, colonnes masquables
// (mémorisées dans le compte, FM14), pagination serveur ou locale. Encapsule
// mantine-datatable (remplaçable sans toucher aux écrans, design §13).
import { useMemo, useState, type ReactNode } from "react";
import { ActionIcon, Checkbox, Group, Menu, Paper, Text, Tooltip } from "@mantine/core";
import {
  DataTable, type DataTableColumn, type DataTableProps, type DataTableSortStatus,
} from "mantine-datatable";
import { IconColumns3 } from "@tabler/icons-react";
import { usePreferences } from "../api/session";
import { compareValues } from "../lib/format";

export type GridColumn<T> = DataTableColumn<T> & {
  accessor: string;
  /** false : colonne toujours visible (absente du choix des colonnes). */
  hideable?: boolean;
  /** Valeur utilisée pour le tri local (par défaut : record[accessor]). */
  sortValue?: (record: T) => unknown;
};

export interface SortState {
  column: string;
  direction: "asc" | "desc";
}

/** « -date » ↔ { column: "date", direction: "desc" } (paramètre `sort` de l'API). */
export function parseSort(value: string | null | undefined): SortState | null {
  if (!value) return null;
  return value.startsWith("-")
    ? { column: value.slice(1), direction: "desc" }
    : { column: value, direction: "asc" };
}

export function formatSort(sort: SortState | null): string {
  if (!sort) return "";
  return sort.direction === "desc" ? `-${sort.column}` : sort.column;
}

interface ServerPagination {
  page: number;
  perPage: number;
  total: number;
  onPageChange: (page: number) => void;
}

export interface DataGridProps<T> {
  /** Clé des préférences du tableau (colonnes masquées). */
  id: string;
  records: T[] | undefined;
  columns: GridColumn<T>[];
  idAccessor?: keyof T & string;
  fetching?: boolean;
  /** Tri contrôlé (serveur) ; sans `onSortChange`, le tri est fait localement. */
  sort?: SortState | null;
  onSortChange?: (sort: SortState) => void;
  defaultSort?: SortState;
  /** Pagination serveur ; sans elle, `perPage` pagine localement (sinon tout est affiché). */
  pagination?: ServerPagination;
  perPage?: number;
  selection?: {
    selected: T[];
    onChange: (records: T[]) => void;
    actions?: (selected: T[]) => ReactNode;
  };
  onRowClick?: (record: T) => void;
  emptyText?: string;
  toolbar?: ReactNode;
}

export function DataGrid<T>({
  id, records, columns, idAccessor = "id" as keyof T & string, fetching, sort, onSortChange,
  defaultSort, pagination, perPage, selection, onRowClick, emptyText = "Aucun élément.", toolbar,
}: DataGridProps<T>) {
  const [preferences, updatePreferences] = usePreferences();
  const hidden = preferences.tables?.[id]?.hidden ?? [];
  const [localSort, setLocalSort] = useState<SortState | null>(defaultSort ?? null);
  const [localPage, setLocalPage] = useState(1);
  const activeSort = onSortChange ? sort ?? null : localSort;

  const sorted = useMemo(() => {
    const rows = records ?? [];
    if (onSortChange || !activeSort) return rows;
    const column = columns.find((c) => c.accessor === activeSort.column);
    const value = column?.sortValue ?? ((r: T) => (r as Record<string, unknown>)[activeSort.column]);
    const factor = activeSort.direction === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => factor * compareValues(value(a), value(b)));
  }, [records, columns, activeSort, onSortChange]);

  const shown = !pagination && perPage ? sorted.slice((localPage - 1) * perPage, localPage * perPage) : sorted;
  const hideable = columns.filter((c) => c.hideable !== false && c.title);
  const visibleColumns = columns.map((c) => ({ ...c, hidden: c.hidden || hidden.includes(c.accessor) }));

  const toggleColumn = (accessor: string) => {
    const next = hidden.includes(accessor) ? hidden.filter((a) => a !== accessor) : [...hidden, accessor];
    updatePreferences({ tables: { [id]: { hidden: next } } });
  };

  // Sans tri actif : accesseur vide (aucune colonne marquée, premier clic = croissant).
  const sortStatus: DataTableSortStatus<T> = activeSort
    ? { columnAccessor: activeSort.column, direction: activeSort.direction }
    : { columnAccessor: "", direction: "asc" };
  const onSortStatusChange = (s: DataTableSortStatus<T>) => {
    const next: SortState = { column: String(s.columnAccessor), direction: s.direction };
    if (onSortChange) onSortChange(next);
    else {
      setLocalSort(next);
      setLocalPage(1);
    }
  };

  const paginationText = ({ from, to, totalRecords }: { from: number; to: number; totalRecords: number }) =>
    `${from}–${to} sur ${totalRecords}`;
  const paginationProps = pagination
    ? { page: pagination.page, onPageChange: pagination.onPageChange, totalRecords: pagination.total,
        recordsPerPage: pagination.perPage, paginationText }
    : perPage && sorted.length > perPage
      ? { page: localPage, onPageChange: setLocalPage, totalRecords: sorted.length, recordsPerPage: perPage,
          paginationText }
      : {};

  const selectionProps = selection
    ? { selectedRecords: selection.selected, onSelectedRecordsChange: selection.onChange }
    : {};

  // Les props de mantine-datatable sont une union (tri, pagination, sélection présents
  // ou absents ensemble) : assemblées ici puis typées d'un bloc.
  const tableProps = {
    withTableBorder: false,
    borderRadius: "sm",
    highlightOnHover: true,
    verticalAlign: "center",
    minHeight: shown.length ? undefined : 150,
    records: shown,
    columns: visibleColumns,
    idAccessor,
    fetching,
    noRecordsText: emptyText,
    loadingText: "Chargement…",
    onRowClick: onRowClick ? ({ record }: { record: T }) => onRowClick(record) : undefined,
    sortStatus,
    onSortStatusChange,
    ...paginationProps,
    ...selectionProps,
  } as unknown as DataTableProps<T>;

  return (
    <Paper withBorder radius="sm">
      <Group justify="space-between" px="sm" py={6} gap="xs" wrap="nowrap">
        <Group gap="xs">
          {selection && selection.selected.length > 0 ? (
            <>
              <Text size="sm" fw={500}>{selection.selected.length} sélectionné(s)</Text>
              {selection.actions?.(selection.selected)}
            </>
          ) : (
            toolbar ?? <Text size="sm" c="dimmed">{(pagination?.total ?? sorted.length)} élément(s)</Text>
          )}
        </Group>
        {hideable.length > 0 && (
          <Menu position="bottom-end" closeOnItemClick={false} withinPortal>
            <Menu.Target>
              <Tooltip label="Colonnes affichées">
                <ActionIcon variant="subtle" color="gray" aria-label="Colonnes affichées">
                  <IconColumns3 size={18} />
                </ActionIcon>
              </Tooltip>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Label>Colonnes</Menu.Label>
              {hideable.map((c) => (
                <Menu.Item key={c.accessor} onClick={() => toggleColumn(c.accessor)}>
                  <Checkbox readOnly size="xs" label={String(c.title)} checked={!hidden.includes(c.accessor)}
                    styles={{ input: { cursor: "pointer" }, label: { cursor: "pointer" } }} />
                </Menu.Item>
              ))}
            </Menu.Dropdown>
          </Menu>
        )}
      </Group>
      <DataTable<T> {...tableProps} />
    </Paper>
  );
}
