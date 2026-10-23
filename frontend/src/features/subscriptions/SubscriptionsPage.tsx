// Achats › Abonnements : contrats récurrents (internet, téléphone, assurance, banque…), coût
// mensuel et annuel, total par catégorie, dernière échéance (facture et prélèvement rattachés),
// échéances manquantes et préavis de résiliation à surveiller.
import { useState } from "react";
import { Alert, Anchor, Button, Checkbox, Group, Paper, Select, SimpleGrid, Text, TextInput, Textarea } from "@mantine/core";
import { useForm } from "@mantine/form";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { Can } from "../../components/Can";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FormModal } from "../../components/FormModal";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink, useGoTo } from "../../app/navigation";
import { PERIOD_TONES, SUBSCRIPTIONS_KEY, type Subscription, type SubscriptionsMeta } from "./types";

const euros = (cents: number) => (cents / 100).toFixed(2).replace(".", ",");

export function SubscriptionForm({ sub, meta, onDone }: { sub: Subscription | null; meta: SubscriptionsMeta; onDone: (item?: Subscription) => void }) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm({ initialValues: {
    label: sub?.label ?? "", entity_id: sub ? String(sub.supplier.id) : "", category: sub?.category ?? "internet",
    amount: sub ? euros(sub.amount_cents) : "", amount_fixed: sub?.amount_fixed ?? true, frequency: sub?.frequency ?? "monthly",
    due_day: String(sub?.due_day ?? 1), start_date: sub?.start_date ?? new Date().toISOString().slice(0, 10),
    end_date: sub?.end_date ?? "", renewal_date: sub?.renewal_date ?? "", notice_days: sub?.notice_days ? String(sub.notice_days) : "",
    product_id: sub?.product_id ?? "", bank_account_id: sub?.bank_account_id ?? "", active: sub?.active ?? true, notes: sub?.notes ?? "",
  } });
  const save = useAction((values: typeof form.values) => {
    const body = { ...values, end_date: values.end_date || null, renewal_date: values.renewal_date || null };
    return sub ? api.patch<{ item: Subscription; notices: Notice[] }>(`/api/v1/subscriptions/${sub.id}`, body)
      : api.post<{ item: Subscription; notices: Notice[] }>("/api/v1/subscriptions", body);
  }, { invalidate: [SUBSCRIPTIONS_KEY], silent: true });
  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values, { onSuccess: (r) => onDone(r.item), onError: (e) => setError(applyApiError(form, e)) }))}>
      <FormBody error={error} submitLabel={sub ? "Enregistrer" : "Créer l'abonnement"} onCancel={() => onDone()} loading={save.isPending}>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput label="Désignation" required placeholder="Box internet, assurance multirisque…" {...form.getInputProps("label")} />
          <Select label="Fournisseur" required searchable data={meta.suppliers} {...form.getInputProps("entity_id")} />
        </SimpleGrid>
        <SimpleGrid cols={{ base: 2, sm: 4 }}>
          <Select label="Catégorie" data={meta.categories} allowDeselect={false} {...form.getInputProps("category")} />
          <TextInput label="Montant TTC (€)" required inputMode="decimal" {...form.getInputProps("amount")} />
          <Select label="Périodicité" data={meta.frequencies} allowDeselect={false} {...form.getInputProps("frequency")} />
          <TextInput label="Jour d'échéance" inputMode="numeric" description="1 à 28" {...form.getInputProps("due_day")} />
        </SimpleGrid>
        <Checkbox label="Montant fixe" description="Sinon estimé : une facture à ±30 % est rattachée." {...form.getInputProps("amount_fixed", { type: "checkbox" })} />
        <SimpleGrid cols={{ base: 2, sm: 4 }}>
          <TextInput label="Début" type="date" required {...form.getInputProps("start_date")} />
          <TextInput label="Fin" type="date" {...form.getInputProps("end_date")} />
          <TextInput label="Reconduction" type="date" description="Tacite, chaque année" {...form.getInputProps("renewal_date")} />
          <TextInput label="Préavis (jours)" inputMode="numeric" {...form.getInputProps("notice_days")} />
        </SimpleGrid>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <Select label="Produit du catalogue" clearable searchable data={meta.products} description="Compte de charge et TVA de la facture"
            {...form.getInputProps("product_id")} />
          <Select label="Compte prélevé" clearable data={meta.bank_accounts} {...form.getInputProps("bank_account_id")} />
        </SimpleGrid>
        {sub && <Checkbox label="Abonnement en cours" {...form.getInputProps("active", { type: "checkbox" })} />}
        <Textarea label="Notes" autosize minRows={2} {...form.getInputProps("notes")} />
      </FormBody>
    </form>
  );
}

export default function SubscriptionsPage() {
  const { data, isFetching } = useList<Subscription, SubscriptionsMeta>(SUBSCRIPTIONS_KEY, "/api/v1/subscriptions");
  const [creating, setCreating] = useState(false);
  const goTo = useGoTo();
  const summary = data?.meta?.summary;
  const columns: GridColumn<Subscription>[] = [
    { accessor: "label", title: "Abonnement", hideable: false, render: (s) => (
      <Group gap={6} wrap="nowrap"><Anchor component={AppLink} href={`/subscriptions/${s.id}`} size="sm">{s.label}</Anchor>
        {s.notice_alert && <span title={`Résiliation avant le ${formatDate(s.notice_deadline)}`}><StatusBadge tone="gap">préavis</StatusBadge></span>}</Group>
    ) },
    { accessor: "supplier", title: "Fournisseur", render: (s) => s.supplier.name },
    { accessor: "category_label", title: "Catégorie" },
    { accessor: "amount_cents", title: "Montant", textAlign: "right", render: (s) => <Text size="sm"><MoneyText cents={s.amount_cents} size="sm" />
      <Text span size="xs" c="dimmed"> {s.frequency_label.toLowerCase()}{s.amount_fixed ? "" : " (estimé)"}</Text></Text> },
    { accessor: "monthly_cents", title: "Par mois", textAlign: "right", render: (s) => <MoneyText cents={s.monthly_cents} size="sm" /> },
    { accessor: "last_period", title: "Dernière échéance", render: (s) => s.last_period
      ? <Group gap={6} wrap="nowrap"><Text size="sm" className="lv-num">{formatDate(s.last_period.due_date)}</Text>
        <StatusBadge tone={PERIOD_TONES[s.last_period.status]}>{s.last_period.status_label}</StatusBadge></Group> : null },
    { accessor: "missing", title: "Manquantes", textAlign: "right", render: (s) => s.missing ? <Text size="sm" c="var(--lv-brique)">{s.missing}</Text> : null },
    { accessor: "active", title: "État", render: (s) => s.active ? null : <StatusBadge tone="neutral">Terminé</StatusBadge> },
  ];
  return (
    <>
      <PageHeader title="Abonnements" description="Contrats récurrents : chaque échéance attend sa facture et son prélèvement, rattachés automatiquement."
        actions={<Can><Button onClick={() => setCreating(true)}>Nouvel abonnement</Button></Can>} />
      {summary && (
        <SimpleGrid cols={{ base: 1, sm: 3 }} mb="md">
          <Paper p="md"><Text size="sm" c="dimmed">Coût mensuel</Text><MoneyText cents={summary.monthly_cents} fw={700} size="xl" /></Paper>
          <Paper p="md"><Text size="sm" c="dimmed">Coût annuel</Text><MoneyText cents={summary.yearly_cents} fw={700} size="xl" /></Paper>
          <Paper p="md"><Text size="sm" c="dimmed">Par catégorie (mois)</Text>
            {summary.by_category.map((c) => <Text key={c.category} size="sm">{c.label} : <MoneyText cents={c.monthly_cents} size="sm" /></Text>)}</Paper>
        </SimpleGrid>
      )}
      {!!summary?.missing && <Alert color="brique" mb="sm">{summary.missing} échéance(s) passée(s) sans facture ni prélèvement : ouvrez l'abonnement pour la rattacher ou l'ignorer.</Alert>}
      {!!summary?.notice_alerts && <Alert color="paille" mb="sm">{summary.notice_alerts} contrat(s) arrivent à la date limite de résiliation dans les 45 jours.</Alert>}
      <DataGrid id="subscriptions" records={data?.items} columns={columns} fetching={isFetching} emptyText="Aucun abonnement." />
      <FormModal opened={creating} onClose={() => setCreating(false)} title="Nouvel abonnement" size="xl">
        {creating && data?.meta && <SubscriptionForm sub={null} meta={data.meta} onDone={(item) => { setCreating(false); if (item) goTo(`/subscriptions/${item.id}`); }} />}
      </FormModal>
    </>
  );
}
