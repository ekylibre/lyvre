// Recettes et dépenses (comptabilité simplifiée) : opérations de l'exercice ou du mois, par
// catégorie, sans débit ni crédit ; saisie et modification en fenêtre ; transactions bancaires
// importées à catégoriser (l'opération est rapprochée aussitôt).
import { useState } from "react";
import { Anchor, Button, Center, Group, Loader, Paper, Select, SimpleGrid, Stack, Table, Tabs, Text, TextInput } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { confirmAction } from "../../components/ConfirmButton";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { FormModal } from "../../components/FormModal";
import { MoneyInput, MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import type { Category } from "./CategoriesPage";

type Kind = "income" | "expense";
interface Row {
  entry_id: number; line_id: number; date: string; label: string; kind: Kind; amount_cents: number; category_id: number | null;
  category: string; bank_account_id: number; bank_account: string; treasury_kind: string; entity_id: number | null;
  entity: string | null; project_id: number | null; project: string | null; reconciled: boolean; editable: boolean;
}
type Option = { value: string; label: string };
interface View {
  fiscal_year: { id: number; label: string; closed: boolean } | null; rows: Row[]; income_cents: number; expense_cents: number;
  balance_cents: number;
  meta: { categories: Category[]; bank_accounts: (Option & { kind: string })[]; entities: Option[]; projects: Option[]; fiscal_years: Option[] };
}
interface Pending { id: number; date: string; label: string; amount_cents: number; bank_account: string; entity_id: number | null; entity: string | null }

const KEY = ["simple-operations"];

export default function OperationsPage() {
  const can = useCan();
  const [params, setParams] = useUrlParams({ fiscal_year_id: "", month: "", category_id: "", kind: "", tab: "operations" });
  const query = new URLSearchParams(Object.entries(params).filter(([k, v]) => v && k !== "tab")).toString();
  const { data } = useQuery({ queryKey: [...KEY, query], placeholderData: (prev) => prev,
    queryFn: () => api.get<View>(`/api/v1/simple/operations?${query}`) });
  const [editing, setEditing] = useState<Row | Kind | null>(null);
  if (!data) return <Center h={300}><Loader /></Center>;
  const categories = data.meta.categories.map((c) => ({ value: String(c.id), label: c.label }));
  return (
    <>
      <PageHeader title="Recettes et dépenses" description={data.fiscal_year ? `Exercice ${data.fiscal_year.label}` : undefined}
        actions={can.write && <>
          <Button variant="default" onClick={() => setEditing("expense")}>Nouvelle dépense</Button>
          <Button onClick={() => setEditing("income")}>Nouvelle recette</Button>
        </>} />
      <Tabs value={params.tab} onChange={(v) => setParams({ ...params, tab: v ?? "operations" })}>
        <Tabs.List mb="md"><Tabs.Tab value="operations">Opérations</Tabs.Tab><Tabs.Tab value="pending">Relevé à catégoriser</Tabs.Tab></Tabs.List>
        <Tabs.Panel value="operations">
          <FilterBar>
            <Select aria-label="Exercice" w={150} data={data.meta.fiscal_years} value={params.fiscal_year_id || (data.fiscal_year ? String(data.fiscal_year.id) : null)}
              allowDeselect={false} onChange={(v) => setParams({ ...params, fiscal_year_id: v ?? "", month: "" })} />
            <TextInput aria-label="Mois" type="month" w={170} value={params.month} onChange={(e) => setParams({ ...params, month: e.currentTarget.value })} />
            <Select aria-label="Sens" w={150} placeholder="Recettes et dépenses" clearable value={params.kind || null}
              data={[{ value: "income", label: "Recettes" }, { value: "expense", label: "Dépenses" }]} onChange={(v) => setParams({ ...params, kind: v ?? "" })} />
            <Select aria-label="Catégorie" w={220} placeholder="Toutes les catégories" clearable searchable data={categories}
              value={params.category_id || null} onChange={(v) => setParams({ ...params, category_id: v ?? "" })} />
          </FilterBar>
          <SimpleGrid cols={{ base: 1, sm: 3 }} mb="md">
            <Paper p="md"><Text size="sm" c="dimmed">Recettes</Text><Text fz={22} fw={500} className="lv-num"><MoneyText cents={data.income_cents} /></Text></Paper>
            <Paper p="md"><Text size="sm" c="dimmed">Dépenses</Text><Text fz={22} fw={500} className="lv-num"><MoneyText cents={data.expense_cents} /></Text></Paper>
            <Paper p="md"><Text size="sm" c="dimmed">Solde</Text><Text fz={22} fw={500} className="lv-num"><MoneyText cents={data.balance_cents} anomaly={data.balance_cents < 0} /></Text></Paper>
          </SimpleGrid>
          <Paper p={0} style={{ overflowX: "auto" }}>
            <Table verticalSpacing={6} miw={820}>
              <Table.Thead bg="var(--lv-sauge)"><Table.Tr><Table.Th>Date</Table.Th><Table.Th>Libellé</Table.Th><Table.Th>Catégorie</Table.Th>
                <Table.Th>Compte</Table.Th><Table.Th>Tiers · projet</Table.Th><Table.Th ta="right">Montant</Table.Th><Table.Th /></Table.Tr></Table.Thead>
              <Table.Tbody>
                {data.rows.map((r) => (
                  <Table.Tr key={r.line_id}>
                    <Table.Td className="lv-num">{formatDate(r.date)}</Table.Td>
                    <Table.Td><Text size="sm">{r.label}</Text>{r.reconciled && <StatusBadge tone="ok">Relevé</StatusBadge>}</Table.Td>
                    <Table.Td><Text size="sm">{r.category}</Text></Table.Td>
                    <Table.Td><Text size="sm">{r.bank_account}</Text></Table.Td>
                    <Table.Td><Text size="xs" c="dimmed">{[r.entity, r.project].filter(Boolean).join(" · ") || "—"}</Text></Table.Td>
                    <Table.Td ta="right"><MoneyText cents={r.amount_cents} plus size="sm" fw={600} /></Table.Td>
                    <Table.Td ta="right">{can.write && r.editable && <Button variant="subtle" size="compact-sm" onClick={() => setEditing(r)}>Modifier</Button>}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
            {data.rows.length === 0 && <Text size="sm" c="dimmed" p="md">Aucune opération sur la période.</Text>}
          </Paper>
        </Tabs.Panel>
        <Tabs.Panel value="pending">{params.tab === "pending" && <ToCategorize view={data} />}</Tabs.Panel>
      </Tabs>
      <FormModal opened={editing !== null} onClose={() => setEditing(null)}
        title={typeof editing === "object" && editing ? "Modifier l'opération" : editing === "income" ? "Nouvelle recette" : "Nouvelle dépense"}>
        {editing !== null && <OperationForm key={typeof editing === "object" ? editing.entry_id : editing} view={data}
          row={typeof editing === "object" ? editing : null} kind={typeof editing === "object" ? editing.kind : editing} onDone={() => setEditing(null)} />}
      </FormModal>
    </>
  );
}

function OperationForm({ view, row, kind, onDone }: { view: View; row: Row | null; kind: Kind; onDone: () => void }) {
  const [when, setWhen] = useState<string | null>(row?.date ?? new Date().toISOString().slice(0, 10));
  const [label, setLabel] = useState(row?.label ?? "");
  const [amount, setAmount] = useState<number | null>(row ? Math.abs(row.amount_cents) : null);
  const [category, setCategory] = useState<string | null>(row?.category_id ? String(row.category_id) : null);
  const [account, setAccount] = useState<string | null>(row ? String(row.bank_account_id) : view.meta.bank_accounts[0]?.value ?? null);
  const [entity, setEntity] = useState<string | null>(row?.entity_id ? String(row.entity_id) : null);
  const [project, setProject] = useState<string | null>(row?.project_id ? String(row.project_id) : null);
  const locked = row?.reconciled ?? false;
  const body = () => ({ date: when, label, amount_cents: amount, category_id: category ? Number(category) : null,
    bank_account_id: account ? Number(account) : null, entity_id: entity ? Number(entity) : null, project_id: project ? Number(project) : null });
  const save = useAction(() => row ? api.put<{ notices: Notice[] }>(`/api/v1/simple/operations/${row.entry_id}`, body())
    : api.post<{ notices: Notice[] }>("/api/v1/simple/operations", body()), { invalidate: [KEY] });
  const remove = useAction(() => api.delete<{ notices: Notice[] }>(`/api/v1/simple/operations/${row!.entry_id}`), { invalidate: [KEY] });
  const categories = view.meta.categories.filter((c) => c.kind === kind).map((c) => ({ value: String(c.id), label: c.label }));
  return (
    <Stack>
      {locked && <Text size="sm" c="dimmed">Opération issue du relevé bancaire : la date, le montant et le compte suivent le relevé.</Text>}
      <Group grow>
        <DateInput label="Date" required valueFormat="DD/MM/YYYY" value={when} onChange={setWhen} disabled={locked} />
        <MoneyInput label="Montant" required value={amount} onChange={setAmount} disabled={locked} />
      </Group>
      <TextInput label="Libellé" required value={label} onChange={(e) => setLabel(e.currentTarget.value)} data-autofocus
        placeholder={kind === "income" ? "Cotisation, don, vente…" : "Achat, loyer, assurance…"} />
      <Select label="Catégorie" required searchable data={categories} value={category} onChange={setCategory}
        description={categories.length ? undefined : "Aucune catégorie : Configuration › Catégories."} />
      <Select label={kind === "income" ? "Encaissé sur" : "Payé depuis"} required allowDeselect={false} disabled={locked}
        data={view.meta.bank_accounts.map((b) => ({ value: b.value, label: b.kind === "cash" ? `${b.label} (espèces)` : b.label }))}
        value={account} onChange={setAccount} />
      <Group grow>
        <Select label="Tiers" clearable searchable data={view.meta.entities} value={entity} onChange={setEntity} />
        {view.meta.projects.length > 0 && <Select label="Projet" clearable searchable data={view.meta.projects} value={project} onChange={setProject} />}
      </Group>
      <Group justify="space-between">
        <div>{row && !locked && <Button variant="subtle" color="brique" onClick={() => confirmAction({
          title: "Supprimer l'opération ?", confirmLabel: "Supprimer", onConfirm: () => remove.mutate(undefined, { onSuccess: onDone }) })}>Supprimer</Button>}</div>
        <Group>
          <Button variant="default" onClick={onDone}>Annuler</Button>
          <Button loading={save.isPending} disabled={!when || !label.trim() || !amount || !category || !account}
            onClick={() => save.mutate(undefined, { onSuccess: onDone })}>Enregistrer</Button>
        </Group>
      </Group>
    </Stack>
  );
}

function ToCategorize({ view }: { view: View }) {
  const can = useCan();
  const { data } = useQuery({ queryKey: [...KEY, "pending"], queryFn: () => api.get<{ items: Pending[] }>("/api/v1/simple/to-categorize") });
  const categorize = useAction(({ id, category }: { id: number; category: string }) =>
    api.post<{ notices: Notice[] }>(`/api/v1/simple/to-categorize/${id}`, { category_id: Number(category) }), { invalidate: [KEY] });
  if (!data) return <Center h={200}><Loader /></Center>;
  const options = (kind: Kind) => view.meta.categories.filter((c) => c.kind === kind).map((c) => ({ value: String(c.id), label: c.label }));
  return (
    <Paper p={0} style={{ overflowX: "auto" }}>
      <Table verticalSpacing={6} miw={720}>
        <Table.Tbody>
          {data.items.map((t) => (
            <Table.Tr key={t.id}>
              <Table.Td className="lv-num" w={100}>{formatDate(t.date)}</Table.Td>
              <Table.Td><Text size="sm">{t.label}</Text><Text size="xs" c="dimmed">{t.bank_account}{t.entity && ` · ${t.entity}`}</Text></Table.Td>
              <Table.Td ta="right"><MoneyText cents={t.amount_cents} plus size="sm" fw={600} /></Table.Td>
              <Table.Td w={260}>{can.write && <Select size="xs" aria-label={`Catégorie de ${t.label}`} placeholder="Choisir la catégorie" searchable
                data={options(t.amount_cents > 0 ? "income" : "expense")} onChange={(v) => v && categorize.mutate({ id: t.id, category: v })} />}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      {data.items.length === 0 && <Text size="sm" c="dimmed" p="md">Tout le relevé est catégorisé. Importez un relevé depuis{" "}
        <Anchor component={AppLink} href="/imports/ofx" size="sm">Imports › OFX</Anchor>.</Text>}
    </Paper>
  );
}
