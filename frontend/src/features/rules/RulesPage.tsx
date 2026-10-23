// Tiers › Règles de catégorisation : ordre d'évaluation, activation, édition, application.
import { useState } from "react";
import {
  ActionIcon, Badge, Button, Checkbox, Group, Select, Stack, Switch, Text, TextInput, Tooltip,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { ArrowDown, ArrowUp } from "lucide-react";
import { api } from "../../api/client";
import { useBookkeeping, useCan } from "../../api/session";
import { useQuery } from "@tanstack/react-query";
import { CATEGORIES_KEY, type Category } from "../simple/CategoriesPage";
import { useAction, useList, type Notice } from "../../api/resources";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { confirmAction } from "../../components/ConfirmButton";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FormDrawer } from "../../components/FormModal";
import { MoneyInput } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { Can } from "../../components/Can";
import { StatusBadge } from "../../components/StatusBadge";
import { formatEuros } from "../../lib/format";
import { useRouteModal } from "../../app/useRouteModal";

export interface Rule {
  id: number; position: number; name: string; label_contains: string | null; label_regex: string | null;
  amount_min_cents: number | null; amount_max_cents: number | null; raw_type: string | null;
  entity_name: string | null; entity_type: string | null; category: string | null;
  account_code: string | null; is_active: boolean; project_id: number | null; project: string | null;
}
interface Option { value: string; label: string }

const KEY = ["rules"];

/** Expression de Python `re` testée en JavaScript (drapeau (?i) en tête pris en charge). */
export function testRegex(pattern: string, sample: string): boolean | string {
  let source = pattern;
  let flags = "";
  if (source.startsWith("(?i)")) {
    source = source.slice(4);
    flags = "i";
  }
  try {
    return new RegExp(source, flags).test(sample);
  } catch (err) {
    return (err as Error).message;
  }
}

function Conditions({ rule }: { rule: Rule }) {
  const chips: string[] = [];
  if (rule.label_contains) chips.push(`contient « ${rule.label_contains} »`);
  if (rule.label_regex) chips.push(rule.label_regex);
  if (rule.amount_min_cents !== null) chips.push(`≥ ${formatEuros(rule.amount_min_cents)}`);
  if (rule.amount_max_cents !== null) chips.push(`≤ ${formatEuros(rule.amount_max_cents)}`);
  if (rule.raw_type) chips.push(`type ${rule.raw_type}`);
  return (
    <Group gap={4}>
      {chips.map((c) => <Badge key={c} variant="outline" color="gray" tt="none" fw={500}>{c}</Badge>)}
    </Group>
  );
}

function RegexTester({ pattern }: { pattern: string }) {
  const [sample, setSample] = useState("");
  const result = pattern && sample ? testRegex(pattern, sample) : null;
  return (
    <Stack gap={4}>
      <TextInput label="Tester l'expression sur un libellé" placeholder="PRELEVEMENT MAIF 12345" size="sm"
        value={sample} onChange={(e) => setSample(e.currentTarget.value)} />
      {result !== null && (
        typeof result === "string"
          ? <StatusBadge tone="gap">Expression invalide</StatusBadge>
          : <StatusBadge tone={result ? "ok" : "neutral"}>{result ? "Le libellé correspond" : "Pas de correspondance"}</StatusBadge>
      )}
    </Stack>
  );
}

function RuleForm({ rule, entityTypes, projects, onDone }: {
  rule: Rule | null; entityTypes: string[]; projects: Option[]; onDone: () => void;
}) {
  const simple = useBookkeeping() === "simple";
  const categories = useQuery({ queryKey: CATEGORIES_KEY, enabled: simple,
    queryFn: () => api.get<{ items: Category[] }>("/api/v1/simple-categories") });
  const [error, setError] = useState<string | null>(null);
  const form = useForm({
    initialValues: {
      name: rule?.name ?? "", label_contains: rule?.label_contains ?? "", label_regex: rule?.label_regex ?? "",
      amount_min_cents: rule?.amount_min_cents ?? null, amount_max_cents: rule?.amount_max_cents ?? null,
      raw_type: rule?.raw_type ?? "", entity_name: rule?.entity_name ?? "", entity_type: rule?.entity_type ?? "",
      category: rule?.category ?? "", account_code: rule?.account_code ?? "", is_active: rule?.is_active ?? true,
      project_id: rule?.project_id ? String(rule.project_id) : null as string | null,
    },
  });
  const save = useAction((values: typeof form.values) => rule
    ? api.patch<{ notices: Notice[] }>(`/api/v1/rules/${rule.id}`, values)
    : api.post<{ notices: Notice[] }>("/api/v1/rules", values), { invalidate: [KEY], silent: true });
  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values, {
      onSuccess: onDone, onError: (e) => setError(applyApiError(form, e)),
    }))}>
      <FormBody error={error} submitLabel={rule ? "Enregistrer" : "Créer la règle"} onCancel={onDone}
        loading={save.isPending}>
        <TextInput label="Nom" required data-autofocus description="Apparaît dans la liste et les journaux."
          {...form.getInputProps("name")} />
        <Text fw={600} size="sm" mt="xs">Conditions (au moins une)</Text>
        <TextInput label="Le libellé contient" description="Sans tenir compte des majuscules."
          placeholder="VIREMENT EN VOTRE FAVEUR MAIF" {...form.getInputProps("label_contains")} />
        <TextInput label="Le libellé correspond à l'expression" description="Expression régulière Python (re)."
          placeholder="(?i)salaire|virement personnel" classNames={{ input: "lv-num" }}
          {...form.getInputProps("label_regex")} />
        {form.values.label_regex && <RegexTester pattern={form.values.label_regex} />}
        <Group grow>
          <MoneyInput label="Montant minimum" value={form.values.amount_min_cents}
            onChange={(v) => form.setFieldValue("amount_min_cents", v)} error={form.errors.amount_min_cents} />
          <MoneyInput label="Montant maximum" value={form.values.amount_max_cents}
            onChange={(v) => form.setFieldValue("amount_max_cents", v)} error={form.errors.amount_max_cents} />
        </Group>
        <TextInput label="Type d'opération" placeholder="DEBIT, CREDIT, INT…" {...form.getInputProps("raw_type")} />
        <Text fw={600} size="sm" mt="xs">Effets</Text>
        <Group grow align="flex-start">
          <TextInput label="Tiers" description="Créé s'il n'existe pas." placeholder="MAIF, URSSAF…"
            {...form.getInputProps("entity_name")} />
          <Select label="Type de tiers" data={entityTypes} clearable {...form.getInputProps("entity_type")} />
        </Group>
        <TextInput label="Catégorie" description="Étiquette libre posée sur la transaction."
          placeholder="Salaires, Assurance, Subventions…" {...form.getInputProps("category")} />
        {simple ? (
          <Select label="Catégorie de l'opération" clearable searchable placeholder="Aucune (transaction à catégoriser)"
            description="Facultatif : la transaction devient une recette ou une dépense de cette catégorie."
            data={(categories.data?.items ?? []).filter((c) => c.active).map((c) => ({ value: c.account.code, label: c.label }))}
            value={form.values.account_code || null} onChange={(v) => form.setFieldValue("account_code", v ?? "")}
            error={form.errors.account_code} />
        ) : (
          <TextInput label="Compte de l'écriture" classNames={{ input: "lv-num" }} placeholder="616 ou 707"
            description="Facultatif : un compte 6 (charge) ou 7 (produit) génère l'écriture."
            {...form.getInputProps("account_code")} />
        )}
        {projects.length > 0 && (
          <Select label="Projet" data={projects} clearable searchable placeholder="Aucun"
            description="Porté sur la ligne de charge ou de produit de l'écriture générée." {...form.getInputProps("project_id")} />
        )}
        <Switch label="Règle active" {...form.getInputProps("is_active", { type: "checkbox" })} />
      </FormBody>
    </form>
  );
}

export default function RulesPage() {
  const can = useCan();
  const modal = useRouteModal("/rules/", "rule_id");
  const [overwrite, setOverwrite] = useState(false);
  const { data, isFetching } = useList<Rule, { entity_types: string[]; projects: Option[] }>(KEY, "/api/v1/rules");
  const editing = modal.mode === "edit" ? data?.items.find((r) => r.id === modal.id) ?? null : null;
  const toggle = useAction((r: Rule) => api.patch<{ notices: Notice[] }>(`/api/v1/rules/${r.id}`, { is_active: !r.is_active }),
    { invalidate: [KEY] });
  const move = useAction(({ rule, direction }: { rule: Rule; direction: "up" | "down" }) =>
    api.post<{ notices?: Notice[] }>(`/api/v1/rules/${rule.id}/move`, { direction }), { invalidate: [KEY] });
  const remove = useAction((r: Rule) => api.delete<{ notices: Notice[] }>(`/api/v1/rules/${r.id}`), { invalidate: [KEY] });
  const apply = useAction(() => api.post<{ notices: Notice[] }>("/api/v1/rules/apply", { overwrite }));
  const items = data?.items ?? [];

  const columns: GridColumn<Rule>[] = [
    { accessor: "position", title: "#", hideable: false, width: 56, render: (r) => <span className="lv-num">{r.position}</span> },
    { accessor: "name", title: "Nom", hideable: false, render: (r) => <Text fw={600} c={r.is_active ? undefined : "dimmed"}>{r.name}</Text> },
    { accessor: "conditions", title: "Conditions", render: (r) => <Conditions rule={r} /> },
    { accessor: "entity_name", title: "Tiers",
      render: (r) => r.entity_name ? <>{r.entity_name}{r.entity_type && <Text span c="dimmed" size="sm"> · {r.entity_type}</Text>}</> : "—" },
    { accessor: "category", title: "Catégorie", render: (r) => r.category ?? "—" },
    { accessor: "account_code", title: "Compte",
      render: (r) => r.account_code
        ? <Text size="sm"><span className="lv-num">{r.account_code}</span> <Text span c="dimmed" size="sm">{r.account_code.startsWith("6") ? "charge" : "produit"}</Text></Text>
        : "—" },
    { accessor: "project", title: "Projet", render: (r) => r.project ?? "—" },
    { accessor: "is_active", title: "Active", hideable: false,
      render: (r) => <Switch checked={r.is_active} aria-label={`Activer la règle ${r.name}`} disabled={!can.write}
        onChange={() => toggle.mutate(r)} /> },
    { accessor: "actions", title: "", hideable: false, textAlign: "right",
      render: (r) => {
        const index = items.findIndex((x) => x.id === r.id);
        return (
          <Group gap={4} justify="flex-end" wrap="nowrap">
            <Tooltip label="Monter"><ActionIcon variant="subtle" color="gray" aria-label={`Monter ${r.name}`}
              disabled={index <= 0} onClick={() => move.mutate({ rule: r, direction: "up" })}><ArrowUp size={16} /></ActionIcon></Tooltip>
            <Tooltip label="Descendre"><ActionIcon variant="subtle" color="gray" aria-label={`Descendre ${r.name}`}
              disabled={index === items.length - 1} onClick={() => move.mutate({ rule: r, direction: "down" })}><ArrowDown size={16} /></ActionIcon></Tooltip>
            <Button variant="subtle" size="compact-sm" onClick={() => modal.openEdit(r.id)}>Modifier</Button>
            <Button variant="subtle" size="compact-sm" color="brique"
              onClick={() => confirmAction({ title: `Supprimer la règle « ${r.name} » ?`, confirmLabel: "Supprimer",
                onConfirm: () => remove.mutate(r) })}>Supprimer</Button>
          </Group>
        );
      } },
  ];

  return (
    <>
      <PageHeader title="Règles de catégorisation"
        description={`${items.length} règle(s), évaluées dans l'ordre : la première qui correspond s'applique.`}
        actions={<>
          <Checkbox label="Réappliquer aux transactions déjà catégorisées" checked={overwrite}
            onChange={(e) => setOverwrite(e.currentTarget.checked)} />
          <Can><Button variant="default" loading={apply.isPending} onClick={() => apply.mutate(undefined)}>Appliquer les règles</Button></Can>
          <Can><Button onClick={modal.openNew}>Créer une règle</Button></Can>
        </>} />
      <DataGrid id="rules" records={items} columns={columns} fetching={isFetching}
        emptyText="Aucune règle : créez-en une pour catégoriser les transactions automatiquement." />
      <FormDrawer opened={modal.mode === "new" || (modal.mode === "edit" && !!editing)} onClose={modal.close}
        title={editing ? `Modifier « ${editing.name} »` : "Créer une règle"}>
        <RuleForm key={editing?.id ?? "new"} rule={editing} entityTypes={data?.meta?.entity_types ?? []}
          projects={data?.meta?.projects ?? []} onDone={modal.close} />
      </FormDrawer>
    </>
  );
}
