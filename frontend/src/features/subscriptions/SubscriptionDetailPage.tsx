// Achats › Abonnement : contrat, reconduction et préavis, échéances attendues avec leur facture et
// leur prélèvement ; rattachement à la main d'une échéance manquante, ou échéance ignorée.
import { useState } from "react";
import { useParams } from "react-router";
import { Anchor, Button, Center, Grid, Group, Loader, Paper, Select, Table, Text, Title } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { FormBody } from "../../components/ApiForm";
import { Can } from "../../components/Can";
import { ConfirmButton } from "../../components/ConfirmButton";
import { FormModal } from "../../components/FormModal";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink, useGoTo } from "../../app/navigation";
import type { Option } from "../purchases/types";
import { SubscriptionForm } from "./SubscriptionsPage";
import { PERIOD_TONES, SUBSCRIPTIONS_KEY, type Period, type Subscription, type SubscriptionsMeta } from "./types";

function LinkForm({ period, onDone }: { period: Period; onDone: (item?: Subscription) => void }) {
  const { data } = useQuery({ queryKey: [...SUBSCRIPTIONS_KEY, "period", period.id],
    queryFn: () => api.get<{ purchases: Option[]; debits: Option[] }>(`/api/v1/subscription-periods/${period.id}/candidates`) });
  const [purchase, setPurchase] = useState<string | null>(null);
  const [debit, setDebit] = useState<string | null>(null);
  const save = useAction(() => api.post<{ item: Subscription; notices: Notice[] }>(`/api/v1/subscription-periods/${period.id}/link`,
    { purchase_id: purchase, bank_transaction_id: debit }));
  return (
    <form onSubmit={(e) => { e.preventDefault(); save.mutate(undefined, { onSuccess: (r) => onDone(r.item) }); }}>
      <FormBody submitLabel="Rattacher" onCancel={() => onDone()} loading={save.isPending}>
        <Text size="sm">Échéance du {formatDate(period.due_date)} — attendu <MoneyText cents={period.expected_cents} size="sm" /></Text>
        <Select label="Facture d'achat du fournisseur" clearable searchable data={data?.purchases ?? []} value={purchase} onChange={setPurchase}
          nothingFoundMessage="Aucune facture du fournisseur autour de l'échéance" />
        <Select label="Prélèvement" clearable searchable data={data?.debits ?? []} value={debit} onChange={setDebit} />
      </FormBody>
    </form>
  );
}

export default function SubscriptionDetailPage() {
  const id = Number(useParams().sub_id);
  const client = useQueryClient();
  const goTo = useGoTo();
  const key = [...SUBSCRIPTIONS_KEY, id];
  const { data } = useQuery({ queryKey: key, queryFn: () => api.get<{ item: Subscription }>(`/api/v1/subscriptions/${id}`) });
  const meta = useList<Subscription, SubscriptionsMeta>(SUBSCRIPTIONS_KEY, "/api/v1/subscriptions").data?.meta;
  const [editing, setEditing] = useState(false);
  const [linking, setLinking] = useState<Period | null>(null);
  const skip = useAction((p: { id: number; skipped: boolean }) => api.post<{ item: Subscription; notices: Notice[] }>(
    `/api/v1/subscription-periods/${p.id}/skip`, { skipped: p.skipped }));
  const remove = useAction(() => api.delete<{ notices: Notice[] }>(`/api/v1/subscriptions/${id}`), { invalidate: [SUBSCRIPTIONS_KEY] });
  if (!data) return <Center h={300}><Loader /></Center>;
  const s = data.item;
  const refresh = (item?: Subscription) => { if (item) client.setQueryData(key, { item }); void client.invalidateQueries({ queryKey: SUBSCRIPTIONS_KEY }); };
  return (
    <>
      <PageHeader title={s.label}
        description={<Group component="span" gap={8}><StatusBadge tone={s.active ? "ok" : "neutral"}>{s.active ? "En cours" : "Terminé"}</StatusBadge>
          <Anchor component={AppLink} href={`/entities/${s.supplier.id}`} size="sm">{s.supplier.name}</Anchor><span>{s.category_label}</span></Group>}
        actions={<>
          <Can>
            <Button variant="default" onClick={() => setEditing(true)}>Modifier</Button>
            <ConfirmButton title="Supprimer cet abonnement ?" confirmLabel="Supprimer" loading={remove.isPending}
              message="Ses échéances sont supprimées ; les factures d'achat restent." onConfirm={() => remove.mutate(undefined, { onSuccess: () => goTo("/subscriptions/") })}>Supprimer</ConfirmButton>
          </Can>
          <Button variant="default" component={AppLink} href="/subscriptions/">Abonnements</Button>
        </>} />
      <Grid mb="md">
        <Grid.Col span={{ base: 12, md: 6 }}><Paper p="md">
          <Group gap="xl">
            <div><Text size="sm" c="dimmed">Montant</Text><MoneyText cents={s.amount_cents} /> <Text span size="xs" c="dimmed">{s.frequency_label.toLowerCase()}{s.amount_fixed ? "" : ", estimé"}</Text></div>
            <div><Text size="sm" c="dimmed">Par mois</Text><MoneyText cents={s.monthly_cents} /></div>
            <div><Text size="sm" c="dimmed">Échéance</Text><Text>le {s.due_day}</Text></div>
          </Group>
          <Text size="sm" mt="xs">Du {formatDate(s.start_date)}{s.end_date ? ` au ${formatDate(s.end_date)}` : ""}</Text>
        </Paper></Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}><Paper p="md">
          <Text size="sm" c="dimmed">Reconduction</Text>
          {s.next_renewal ? <Text>Prochaine le {formatDate(s.next_renewal)}{s.notice_deadline && <> — résiliation avant le <b>{formatDate(s.notice_deadline)}</b></>}</Text>
            : <Text size="sm" c="dimmed">Non renseignée.</Text>}
          {s.notice_alert && <StatusBadge tone="gap">préavis bientôt</StatusBadge>}
          {s.notes && <Text size="sm" mt="xs">{s.notes}</Text>}
        </Paper></Grid.Col>
      </Grid>
      <Paper p="md">
        <Title order={3} mb="xs">Échéances</Title>
        <Table>
          <Table.Thead><Table.Tr><Table.Th>Échéance</Table.Th><Table.Th ta="right">Attendu</Table.Th><Table.Th>Facture</Table.Th>
            <Table.Th>Prélèvement</Table.Th><Table.Th>État</Table.Th><Table.Th /></Table.Tr></Table.Thead>
          <Table.Tbody>
            {(s.periods ?? []).map((p) => (
              <Table.Tr key={p.id}>
                <Table.Td className="lv-num">{formatDate(p.due_date)}</Table.Td>
                <Table.Td ta="right"><MoneyText cents={p.expected_cents} size="sm" /></Table.Td>
                <Table.Td>{p.purchase ? <Anchor component={AppLink} href={`/purchases/${p.purchase.id}`} size="sm">
                  {p.purchase.number ?? "sans numéro"} (<MoneyText cents={p.purchase.total_cents} size="sm" />)</Anchor> : <Text size="sm" c="dimmed">—</Text>}</Table.Td>
                <Table.Td>{p.transaction ? <Text size="sm">{formatDate(p.transaction.date)} · <MoneyText cents={-p.transaction.amount_cents} size="sm" /></Text>
                  : <Text size="sm" c="dimmed">—</Text>}</Table.Td>
                <Table.Td><StatusBadge tone={PERIOD_TONES[p.status]}>{p.status_label}</StatusBadge></Table.Td>
                <Table.Td ta="right"><Can><Group gap={4} justify="flex-end" wrap="nowrap">
                  {p.status !== "paid" && <Button size="compact-sm" variant="subtle" onClick={() => setLinking(p)}>Rattacher</Button>}
                  {(p.status === "missing" || p.status === "expected") &&
                    <Button size="compact-sm" variant="subtle" onClick={() => skip.mutate({ id: p.id, skipped: true }, { onSuccess: (r) => refresh(r.item) })}>Ignorer</Button>}
                  {p.status === "skipped" &&
                    <Button size="compact-sm" variant="subtle" onClick={() => skip.mutate({ id: p.id, skipped: false }, { onSuccess: (r) => refresh(r.item) })}>Rétablir</Button>}
                </Group></Can></Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Paper>
      <FormModal opened={editing} onClose={() => setEditing(false)} title={`Modifier ${s.label}`} size="xl">
        {editing && meta && <SubscriptionForm sub={s} meta={meta} onDone={(item) => { setEditing(false); refresh(item); }} />}
      </FormModal>
      <FormModal opened={!!linking} onClose={() => setLinking(null)} title="Rattacher l'échéance">
        {linking && <LinkForm period={linking} onDone={(item) => { setLinking(null); refresh(item); }} />}
      </FormModal>
    </>
  );
}
