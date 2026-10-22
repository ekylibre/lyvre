// Compta › Budget : grille comptes × mois d'un exercice, budget général ou d'un projet. Chaque
// compte (6 ou 7, regroupement admis) se saisit en annuel (réparti par douzièmes) ou par mois ;
// copie de l'exercice précédent (budget ou réalisé) à relire avant d'enregistrer.
import { useEffect, useMemo, useState } from "react";
import { ActionIcon, Button, Center, Group, Loader, Menu, Paper, SegmentedControl, Select, Table, Text } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { MoneyInput, MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { FISCAL_YEARS_KEY, type FiscalYear } from "../fiscal-years/FiscalYearsPage";

interface Row {
  account_id: number; code: string; label: string; kind: "expense" | "income"; mode: "annual" | "monthly";
  annual_cents: number | null; months: number[]; total_cents: number;
}
interface BudgetView {
  fiscal_year: { id: number; label: string; closed: boolean }; project_id: number | null;
  months: { index: number; label: string; start: string }[]; rows: Row[];
  totals: { expense_cents: number; income_cents: number; result_cents: number };
  previous_fiscal_year: string | null;
  accounts?: { value: string; label: string; code: string }[]; projects?: { value: string; label: string }[];
}

const KEY = ["budgets"];
// Colonne des comptes figée pendant le défilement horizontal des mois.
// zIndex au-dessus des sections droites (« € ») des champs, elles-mêmes à 1.
const STICKY = { position: "sticky", left: 0, zIndex: 3, background: "var(--lv-surface)" } as const;

export function spread(annual: number, count: number): number[] {
  const base = Math.floor(annual / count);
  const rest = annual - base * count;
  return Array.from({ length: count }, (_v, i) => base + (i < rest ? 1 : 0));
}

function withTotal(row: Row, count: number): Row {
  const months = row.mode === "annual" ? spread(row.annual_cents ?? 0, count) : row.months;
  return { ...row, months, total_cents: months.reduce((s, v) => s + v, 0) };
}

export default function BudgetPage() {
  const years = useList<FiscalYear>(FISCAL_YEARS_KEY, "/api/v1/fiscal-years");
  const [params, setParams] = useUrlParams({ fiscal_year_id: "", project_id: "" });
  const defaultYear = years.data?.items.find((fy) => fy.status === "open") ?? years.data?.items[0];
  const fyId = params.fiscal_year_id || (defaultYear ? String(defaultYear.id) : "");
  const query = `/api/v1/budgets/${fyId}${params.project_id ? `?project_id=${params.project_id}` : ""}`;
  const { data } = useQuery({ queryKey: [...KEY, query], enabled: !!fyId, queryFn: () => api.get<BudgetView>(query) });
  return (
    <>
      <PageHeader title="Budget" description="Montants prévus par compte de charge et de produit, en annuel ou par mois." />
      <FilterBar>
        <Select aria-label="Exercice" w={180} allowDeselect={false} value={fyId || null}
          data={(years.data?.items ?? []).map((fy) => ({ value: String(fy.id), label: `Exercice ${fy.label}` }))}
          onChange={(v) => setParams({ ...params, fiscal_year_id: v ?? "" })} />
        <Select aria-label="Projet" w={240} placeholder="Budget général" clearable value={params.project_id || null}
          data={data?.projects ?? []} onChange={(v) => setParams({ ...params, project_id: v ?? "" })} />
      </FilterBar>
      {data ? <BudgetGrid key={query} view={data} query={query} /> : <Center h={200}><Loader /></Center>}
    </>
  );
}

function BudgetGrid({ view, query }: { view: BudgetView; query: string }) {
  const can = useCan();
  const client = useQueryClient();
  const count = view.months.length;
  const [rows, setRows] = useState<Row[]>(view.rows);
  const [dirty, setDirty] = useState(false);
  const [adding, setAdding] = useState<string | null>(null);
  useEffect(() => { setRows(view.rows); setDirty(false); }, [view]);

  const change = (next: Row[]) => { setRows(next.map((r) => withTotal(r, count))); setDirty(true); };
  const update = (accountId: number, patch: Partial<Row>) => change(rows.map((r) => (r.account_id === accountId ? { ...r, ...patch } : r)));
  const save = useAction(() => api.put<BudgetView & { notices: Notice[] }>(`/api/v1/budgets/${view.fiscal_year.id}`, {
    project_id: view.project_id,
    rows: rows.map((r) => (r.mode === "annual" ? { account_id: r.account_id, annual_cents: r.annual_cents ?? 0 }
      : { account_id: r.account_id, months: r.months })),
  }), { invalidate: [KEY] });
  const copy = async (source: "budget" | "actual") => {
    const url = `/api/v1/budgets/${view.fiscal_year.id}/copy?source=${source}${view.project_id ? `&project_id=${view.project_id}` : ""}`;
    const proposal = await client.fetchQuery({ queryKey: ["budget-copy", url], staleTime: 0, queryFn: () => api.get<BudgetView>(url) });
    change(proposal.rows);
  };

  const sections = useMemo(() => ([
    { kind: "expense", title: "Charges", rows: rows.filter((r) => r.kind === "expense") },
    { kind: "income", title: "Produits", rows: rows.filter((r) => r.kind === "income") },
  ] as const), [rows]);
  const sum = (list: Row[], i?: number) => list.reduce((s, r) => s + (i === undefined ? r.total_cents : r.months[i]), 0);
  const expense = sections[0].rows, income = sections[1].rows;
  const used = new Set(rows.map((r) => String(r.account_id)));
  const options = (view.accounts ?? []).filter((a) => !used.has(a.value));
  const editable = can.write;

  const addAccount = (value: string | null) => {
    const account = view.accounts?.find((a) => a.value === value);
    if (!account) return;
    const [, label] = account.label.split(" — ");
    const row: Row = { account_id: Number(account.value), code: account.code, label: label ?? account.label,
      kind: account.code.startsWith("6") ? "expense" : "income", mode: "annual", annual_cents: 0,
      months: Array<number>(count).fill(0), total_cents: 0 };
    change([...rows, row].sort((a, b) => (a.kind === b.kind ? a.code.localeCompare(b.code) : a.kind === "expense" ? -1 : 1)));
    setAdding(null);
  };

  return (
    <>
      {editable && (
        <Group mb="sm" justify="space-between">
          <Group>
            <Select aria-label="Ajouter un compte" placeholder="Ajouter un compte (6 ou 7)…" searchable w={320}
              data={options} value={adding} onChange={addAccount} nothingFoundMessage="Aucun compte" />
            {view.previous_fiscal_year && (
              <Menu>
                <Menu.Target><Button variant="default">Copier {view.previous_fiscal_year}…</Button></Menu.Target>
                <Menu.Dropdown>
                  <Menu.Item onClick={() => void copy("budget")}>Budget {view.previous_fiscal_year}</Menu.Item>
                  <Menu.Item onClick={() => void copy("actual")}>Réalisé {view.previous_fiscal_year}</Menu.Item>
                </Menu.Dropdown>
              </Menu>
            )}
          </Group>
          <Group>
            {dirty && <Text size="sm" c="var(--lv-paille-ink)">Modifications non enregistrées</Text>}
            <Button variant="default" disabled={!dirty} onClick={() => { setRows(view.rows); setDirty(false); }}>Annuler</Button>
            <Button disabled={!dirty} loading={save.isPending} onClick={() => save.mutate(undefined, {
              onSuccess: (saved) => { setRows(saved.rows); setDirty(false); client.setQueryData([...KEY, query], { ...view, ...saved }); },
            })}>Enregistrer</Button>
          </Group>
        </Group>
      )}
      <Paper p={0}>
        <Table.ScrollContainer minWidth={420 + count * 104}>
          <Table verticalSpacing={4} striped={false}>
            <Table.Thead bg="var(--lv-sauge)">
              <Table.Tr>
                <Table.Th miw={220} style={{ ...STICKY, background: "var(--lv-sauge)" }}>Compte</Table.Th>
                {editable && <Table.Th w={150}>Saisie</Table.Th>}
                {view.months.map((m) => <Table.Th key={m.index} ta="right">{m.label}</Table.Th>)}
                <Table.Th ta="right">Total</Table.Th>
                {editable && <Table.Th />}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {sections.map((section) => (
                <SectionRows key={section.kind} title={section.title} rows={section.rows} editable={editable}
                  onUpdate={update} onRemove={(id) => change(rows.filter((r) => r.account_id !== id))} sum={sum}
                  colSpan={count + (editable ? 4 : 2)} />
              ))}
              <Table.Tr fw={700}>
                <Table.Td style={STICKY}>Résultat prévu</Table.Td>
                {editable && <Table.Td />}
                {view.months.map((m, i) => <Table.Td key={m.index} ta="right"><MoneyText cents={sum(income, i) - sum(expense, i)} size="sm" /></Table.Td>)}
                <Table.Td ta="right"><MoneyText cents={sum(income) - sum(expense)} anomaly={sum(income) < sum(expense)} /></Table.Td>
                {editable && <Table.Td />}
              </Table.Tr>
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Paper>
      {rows.length === 0 && <Text size="sm" c="dimmed" mt="sm">Aucun montant prévu : ajoutez des comptes ou copiez l'exercice précédent.</Text>}
    </>
  );
}

function SectionRows({ title, rows, editable, onUpdate, onRemove, sum, colSpan }: {
  title: string; rows: Row[]; editable: boolean; colSpan: number;
  onUpdate: (accountId: number, patch: Partial<Row>) => void; onRemove: (accountId: number) => void;
  sum: (list: Row[], i?: number) => number;
}) {
  const count = rows[0]?.months.length ?? 0;
  return (
    <>
      <Table.Tr>
        <Table.Td style={STICKY}><Text fw={700} size="sm">{title}</Text></Table.Td>
        <Table.Td colSpan={colSpan - 1} />
      </Table.Tr>
      {rows.map((r) => (
        <Table.Tr key={r.account_id}>
          <Table.Td style={STICKY}><Text size="sm"><span className="lv-num">{r.code}</span> <Text span c="dimmed" size="sm">{r.label}</Text></Text></Table.Td>
          {editable && (
            <Table.Td>
              <SegmentedControl size="xs" value={r.mode} aria-label={`Saisie ${r.code}`}
                data={[{ value: "annual", label: "Annuel" }, { value: "monthly", label: "Mensuel" }]}
                onChange={(mode) => onUpdate(r.account_id, mode === "annual"
                  ? { mode: "annual", annual_cents: r.total_cents } : { mode: "monthly", months: r.months })} />
            </Table.Td>
          )}
          {r.months.map((value, i) => (
            <Table.Td key={i} ta="right">
              {editable && r.mode === "monthly"
                ? <MoneyInput aria-label={`${r.code}, mois ${i + 1}`} size="xs" w={96} value={value}
                    onChange={(v) => onUpdate(r.account_id, { months: r.months.map((m, j) => (j === i ? v ?? 0 : m)) })} />
                : <Text size="sm" c={r.mode === "annual" ? "dimmed" : undefined}><MoneyText cents={value} size="sm" /></Text>}
            </Table.Td>
          ))}
          <Table.Td ta="right">
            {editable && r.mode === "annual"
              ? <MoneyInput aria-label={`${r.code}, annuel`} size="xs" w={110} value={r.annual_cents}
                  onChange={(v) => onUpdate(r.account_id, { annual_cents: v ?? 0 })} />
              : <MoneyText cents={r.total_cents} fw={600} />}
          </Table.Td>
          {editable && <Table.Td><ActionIcon variant="subtle" color="brique" aria-label={`Retirer ${r.code}`}
            onClick={() => onRemove(r.account_id)}>×</ActionIcon></Table.Td>}
        </Table.Tr>
      ))}
      {rows.length > 0 && (
        <Table.Tr>
          <Table.Td style={STICKY}><Text size="sm" fw={600}>Total {title.toLowerCase()}</Text></Table.Td>
          {editable && <Table.Td />}
          {Array.from({ length: count }, (_v, i) => <Table.Td key={i} ta="right"><MoneyText cents={sum(rows, i)} size="sm" fw={600} /></Table.Td>)}
          <Table.Td ta="right"><MoneyText cents={sum(rows)} fw={700} /></Table.Td>
          {editable && <Table.Td />}
        </Table.Tr>
      )}
    </>
  );
}
