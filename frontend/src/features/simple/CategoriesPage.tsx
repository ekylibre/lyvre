// Configuration › Catégories (comptabilité simplifiée) : catégories de recettes et de dépenses,
// chacune rattachée à un compte du plan (l'écriture générée l'utilise) ; ordre, activation.
import { useState } from "react";
import { ActionIcon, Button, Center, Group, Loader, Paper, Select, SimpleGrid, Switch, Table, Text, TextInput, Title } from "@mantine/core";
import { ArrowDown, ArrowUp } from "lucide-react";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { FormModal } from "../../components/FormModal";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";

export interface Category {
  id: number; code: string; label: string; kind: "income" | "expense"; position: number; active: boolean; usage?: number;
  account: { id: number; code: string; label: string };
}
interface Meta { income_accounts: { value: string; label: string }[]; expense_accounts: { value: string; label: string }[] }

export const CATEGORIES_KEY = ["simple-categories"];

export default function CategoriesPage() {
  const can = useCan();
  const { data } = useList<Category, Meta>(CATEGORIES_KEY, "/api/v1/simple-categories");
  const [editing, setEditing] = useState<Category | "income" | "expense" | null>(null);
  const move = useAction(({ id, direction }: { id: number; direction: "up" | "down" }) =>
    api.post<{ notices?: Notice[] }>(`/api/v1/simple-categories/${id}/move`, { direction }), { invalidate: [CATEGORIES_KEY] });
  if (!data) return <Center h={300}><Loader /></Center>;
  const sections = [{ kind: "income" as const, title: "Recettes" }, { kind: "expense" as const, title: "Dépenses" }];
  return (
    <>
      <PageHeader title="Catégories" description="Recettes et dépenses de la comptabilité simplifiée ; chaque catégorie correspond à un compte du plan associatif." />
      <SimpleGrid cols={{ base: 1, lg: 2 }}>
        {sections.map((s) => {
          const rows = data.items.filter((c) => c.kind === s.kind);
          return (
            <Paper p={0} key={s.kind}>
              <Group justify="space-between" p="sm"><Title order={2} size="h4">{s.title}</Title>
                {can.write && <Button size="compact-sm" variant="default" onClick={() => setEditing(s.kind)}>Ajouter</Button>}</Group>
              <Table verticalSpacing={4}>
                <Table.Tbody>
                  {rows.map((c, i) => (
                    <Table.Tr key={c.id} style={{ opacity: c.active ? 1 : 0.55 }}>
                      <Table.Td><Text size="sm" fw={500}>{c.label}</Text>{!c.active && <StatusBadge tone="neutral">Inactive</StatusBadge>}</Table.Td>
                      <Table.Td><Text size="xs" c="dimmed"><span className="lv-num">{c.account.code}</span> {c.account.label}</Text></Table.Td>
                      <Table.Td ta="right"><Text size="xs" c="dimmed">{c.usage ?? 0} opération(s)</Text></Table.Td>
                      {can.write && <Table.Td ta="right" style={{ whiteSpace: "nowrap" }}>
                        <ActionIcon variant="subtle" size="sm" aria-label={`Monter ${c.label}`} disabled={i === 0}
                          onClick={() => move.mutate({ id: c.id, direction: "up" })}><ArrowUp size={14} /></ActionIcon>
                        <ActionIcon variant="subtle" size="sm" aria-label={`Descendre ${c.label}`} disabled={i === rows.length - 1}
                          onClick={() => move.mutate({ id: c.id, direction: "down" })}><ArrowDown size={14} /></ActionIcon>
                        <Button variant="subtle" size="compact-sm" onClick={() => setEditing(c)}>Modifier</Button>
                      </Table.Td>}
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Paper>
          );
        })}
      </SimpleGrid>
      <FormModal opened={editing !== null} onClose={() => setEditing(null)}
        title={typeof editing === "object" && editing ? `Modifier « ${editing.label} »` : editing === "income" ? "Nouvelle catégorie de recette" : "Nouvelle catégorie de dépense"}>
        {editing !== null && <CategoryForm key={typeof editing === "object" ? editing.id : editing} category={typeof editing === "object" ? editing : null}
          kind={typeof editing === "object" ? editing.kind : editing} meta={data.meta!} onDone={() => setEditing(null)} />}
      </FormModal>
    </>
  );
}

function CategoryForm({ category, kind, meta, onDone }: { category: Category | null; kind: "income" | "expense"; meta: Meta; onDone: () => void }) {
  const [label, setLabel] = useState(category?.label ?? "");
  const [account, setAccount] = useState<string | null>(category ? String(category.account.id) : null);
  const [active, setActive] = useState(category?.active ?? true);
  const save = useAction(() => {
    const body = { label, kind, account_id: account ? Number(account) : null, active };
    return category ? api.put<{ notices: Notice[] }>(`/api/v1/simple-categories/${category.id}`, body)
      : api.post<{ notices: Notice[] }>("/api/v1/simple-categories", body);
  }, { invalidate: [CATEGORIES_KEY] });
  return (
    <>
      <TextInput label="Libellé" required value={label} onChange={(e) => setLabel(e.currentTarget.value)} data-autofocus mb="sm" />
      <Select label={kind === "income" ? "Compte de produit" : "Compte de charge"} required searchable mb="sm" value={account} onChange={setAccount}
        data={kind === "income" ? meta.income_accounts : meta.expense_accounts} />
      <Switch label="Proposée à la saisie" checked={active} onChange={(e) => setActive(e.currentTarget.checked)} mb="md" />
      <Group justify="flex-end">
        <Button variant="default" onClick={onDone}>Annuler</Button>
        <Button loading={save.isPending} disabled={!label.trim() || !account} onClick={() => save.mutate(undefined, { onSuccess: onDone })}>Enregistrer</Button>
      </Group>
    </>
  );
}
