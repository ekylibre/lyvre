// Fiche d'un tiers : identité, solde fournisseur, factures d'achat, commandes de caisse,
// factures clients, temps de travaux, HelloAsso.
import { useState, type ReactNode } from "react";
import { useParams } from "react-router";
import {
  Accordion, Anchor, Button, Center, Group, Loader, Paper, SimpleGrid, Stack, Table, Text, Title,
} from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { FormDrawer } from "../../components/FormModal";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { Can } from "../../components/Can";
import { StatusBadge, type Tone } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { EntityForm } from "./EntityForm";
import { TIERS_KEY, type EntitiesMeta, type Entity } from "./types";

interface PosOrder {
  id: number; name: string; date: string | null; session: string | null; state: string | null;
  state_label: string | null; amount_total_cents: number;
  lines: { product: string; qty: number; price_unit_cents: number; discount: number; subtotal_cents: number; subtotal_incl_cents: number }[];
  payments: { date: string | null; method: string | null; card_type: string | null; reference: string | null; amount_cents: number }[];
}
interface Detail {
  item: Entity; meta: EntitiesMeta;
  supplier: { account_code: string | null; balance_cents: number | null };
  purchases: { id: number; url: string; issue_date: string | null; invoice_number: string | null;
    is_credit_note: boolean; is_hidden: boolean; total_cents: number; state: string }[];
  pos_orders: PosOrder[];
  customer_invoices: { id: number; url: string; date: string | null; name: string; ref: string | null;
    amount_total_cents: number; amount_residual_cents: number; state: string | null; state_label: string | null;
    payment_state: string | null; payment_state_label: string | null }[];
  work_times: { id: number; date: string; task_type: string; hours: number; valuation_cents: number; notes: string | null }[];
  helloasso: {
    orders: { date: string | null; form_slug: string | null; form_type: string | null; amount_total_cents: number; payer: string }[];
    items: { name: string | null; type: string | null; state: string | null; amount_cents: number; beneficiary: string }[];
    payments: { date: string | null; means: string | null; state: string | null; amount_cents: number }[];
  };
}

const ORDER_TONES: Record<string, Tone> = { done: "ok", invoiced: "ok", paid: "info", cancel: "gap" };
const PAYMENT_TONES: Record<string, Tone> = { paid: "ok", partial: "todo", in_payment: "info", not_paid: "gap" };

const hours = (h: number) => `${h.toFixed(2).replace(".", ",")} h`;

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Stack gap="xs" mt="lg">
      <Title order={2} size="h3">{title}</Title>
      {children}
    </Stack>
  );
}

function SimpleTable({ head, rows, foot }: { head: ReactNode[]; rows: ReactNode[][]; foot?: ReactNode[] }) {
  return (
    <Paper p={0} style={{ overflowX: "auto" }}>
      <Table highlightOnHover verticalSpacing="xs">
        <Table.Thead bg="var(--lv-sauge)"><Table.Tr>{head.map((h, i) => <Table.Th key={i}>{h}</Table.Th>)}</Table.Tr></Table.Thead>
        <Table.Tbody>{rows.map((r, i) => <Table.Tr key={i}>{r.map((c, j) => <Table.Td key={j}>{c}</Table.Td>)}</Table.Tr>)}</Table.Tbody>
        {foot && <Table.Tfoot><Table.Tr>{foot.map((f, i) => <Table.Th key={i}>{f}</Table.Th>)}</Table.Tr></Table.Tfoot>}
      </Table>
    </Paper>
  );
}

const num = (text: ReactNode) => <span className="lv-num">{text}</span>;
const right = (node: ReactNode) => <Text ta="right" inherit component="div">{node}</Text>;

export default function EntityDetailPage() {
  const id = Number(useParams().entity_id);
  const [editing, setEditing] = useState(false);
  const { data, isPending } = useQuery({
    queryKey: [...TIERS_KEY, id], queryFn: () => api.get<Detail>(`/api/v1/tiers/${id}`),
  });
  const odooNote = useAction(() => api.post<{ notices: Notice[] }>(`/api/v1/tiers/${id}/odoo-note`));
  if (isPending || !data) return <Center h={300}><Loader /></Center>;
  const e = data.item;
  const types = Object.fromEntries(data.meta.types.map((t) => [t.value, t.label]));
  const identity = [
    types[e.entity_type] ?? e.entity_type, e.email,
    e.account_code && `compte ${e.account_code}`, e.vat_number && `TVA ${e.vat_number}`,
    e.siret && `SIRET ${e.siret}`, e.default_product && `produit par défaut : ${e.default_product}`,
    e.person_kind && (e.person_kind === "individual" ? "particulier" : "entreprise ou organisme"),
    [e.address_line1, e.address_line2, [e.postal_code, e.city].filter(Boolean).join(" "), e.country]
      .filter(Boolean).join(", "),
  ].filter(Boolean).join(" · ");
  const balance = data.supplier.balance_cents;
  const totalHours = data.work_times.reduce((s, w) => s + w.hours, 0);
  const totalValuation = data.work_times.reduce((s, w) => s + w.valuation_cents, 0);

  return (
    <>
      <PageHeader
        title={<Group gap="sm">{e.name}{e.is_member && <StatusBadge tone="ok">Adhérent</StatusBadge>}{e.is_benevole && <StatusBadge tone="info">Bénévole</StatusBadge>}</Group>}
        description={identity}
        actions={<>
          {e.is_member && (
            <Can><Button variant="default" loading={odooNote.isPending} disabled={!data.meta.integrations.odoo.available}
              title="Écrire la date anniversaire et le statut d'adhésion dans « Notes interne » d'Odoo"
              onClick={() => odooNote.mutate(undefined)}>Mettre à jour la fiche Odoo</Button></Can>
          )}
          <Button variant="default" component={AppLink} href="/entities/">Retour à la liste</Button>
          <Can><Button onClick={() => setEditing(true)}>Modifier</Button></Can>
        </>} />
      {e.notes && <Text c="dimmed" mb="md">{e.notes}</Text>}

      <SimpleGrid cols={{ base: 1, sm: 3 }} mb="md">
        <Paper p="md"><Text size="sm" c="dimmed">Adhésion HelloAsso</Text><Text className="lv-num" size="lg">{formatDate(e.last_helloasso_membership)}</Text></Paper>
        <Paper p="md"><Text size="sm" c="dimmed">Adhésion caisse</Text><Text className="lv-num" size="lg">{formatDate(e.last_pos_membership)}</Text></Paper>
        <Paper p="md">
          <Text size="sm" c="dimmed">Solde fournisseur{data.supplier.account_code && ` (${data.supplier.account_code})`}</Text>
          {balance === null ? <Text size="lg">—</Text> : (
            <Text size="lg"><MoneyText cents={balance} /> <Text span size="sm" c="dimmed">{balance > 0 ? "dû" : balance < 0 ? "en notre faveur" : ""}</Text></Text>
          )}
        </Paper>
      </SimpleGrid>

      {data.purchases.length > 0 && (
        <Section title={`Factures d'achat (${data.purchases.length})`}>
          <SimpleTable head={["Date", "Numéro", right("TTC"), "État"]} rows={data.purchases.map((p) => [
            num(formatDate(p.issue_date)),
            <Anchor href={p.url}>{p.invoice_number ?? "sans numéro"}{p.is_credit_note && " (avoir)"}</Anchor>,
            right(<MoneyText cents={p.is_credit_note ? -p.total_cents : p.total_cents} />), p.state])} />
        </Section>
      )}

      {data.pos_orders.length > 0 && (
        <Section title={`Commandes de caisse Odoo (${data.pos_orders.length})`}>
          <Accordion variant="separated">
            {data.pos_orders.map((o) => (
              <Accordion.Item key={o.id} value={String(o.id)}>
                <Accordion.Control>
                  <Group justify="space-between" wrap="nowrap" pr="sm">
                    <Text fw={600}>{o.name} <Text span c="dimmed" size="sm">{formatDate(o.date)}{o.session && ` · session ${o.session}`}</Text></Text>
                    <Group gap="sm"><StatusBadge tone={ORDER_TONES[o.state ?? ""] ?? "neutral"}>{o.state_label ?? "—"}</StatusBadge><MoneyText cents={o.amount_total_cents} fw={600} /></Group>
                  </Group>
                </Accordion.Control>
                <Accordion.Panel>
                  <SimpleTable head={["Produit", right("Qté"), right("PU"), right("Remise %"), right("HT"), right("TTC")]}
                    rows={o.lines.map((l) => [l.product, right(num(l.qty)), right(<MoneyText cents={l.price_unit_cents} />),
                      right(num(l.discount)), right(<MoneyText cents={l.subtotal_cents} />), right(<MoneyText cents={l.subtotal_incl_cents} />)])} />
                  <Text size="sm" fw={600} mt="sm" mb={4}>Paiements</Text>
                  <SimpleTable head={["Date", "Mode", "Carte", "Référence", right("Montant")]}
                    rows={o.payments.map((p) => [num(formatDate(p.date)), p.method ?? "—", p.card_type ?? "",
                      num(p.reference ?? ""), right(<MoneyText cents={p.amount_cents} />)])} />
                </Accordion.Panel>
              </Accordion.Item>
            ))}
          </Accordion>
        </Section>
      )}

      {data.customer_invoices.length > 0 && (
        <Section title={`Factures clients (${data.customer_invoices.length})`}>
          <SimpleTable head={["Date", "Numéro", "Référence", right("TTC"), right("Reste dû"), "État", "Paiement"]}
            rows={data.customer_invoices.map((inv) => [
              num(formatDate(inv.date)), <Anchor href={inv.url}>{inv.name}</Anchor>, inv.ref ?? "",
              right(<MoneyText cents={inv.amount_total_cents} />),
              right(<MoneyText cents={inv.amount_residual_cents} anomaly={inv.amount_residual_cents > 0 && inv.state === "posted"} />),
              <StatusBadge tone={inv.state === "posted" ? "ok" : inv.state === "cancel" ? "gap" : "neutral"}>{inv.state_label ?? "—"}</StatusBadge>,
              <StatusBadge tone={PAYMENT_TONES[inv.payment_state ?? ""] ?? "neutral"}>{inv.payment_state_label ?? "—"}</StatusBadge>,
            ])} />
        </Section>
      )}

      {(e.is_benevole || data.work_times.length > 0) && (
        <Section title={`Temps de travaux (${data.work_times.length})`}>
          {data.work_times.length ? (
            <SimpleTable head={["Date", "Tâche", right("Heures"), right("Valorisation"), "Notes"]}
              rows={data.work_times.map((w) => [num(formatDate(w.date)), w.task_type, right(num(hours(w.hours))),
                right(<MoneyText cents={w.valuation_cents} />), <Text size="sm" c="dimmed">{w.notes ?? ""}</Text>])}
              foot={["", "Total", right(num(hours(totalHours))), right(<MoneyText cents={totalValuation} />), ""]} />
          ) : <Text c="dimmed" size="sm">Aucun temps saisi pour ce bénévole.</Text>}
        </Section>
      )}

      {e.is_member && (
        <Section title="HelloAsso">
          {data.helloasso.orders.length ? (
            <SimpleTable head={["Date", "Formulaire", "Type", right("Montant"), "Payeur"]}
              rows={data.helloasso.orders.map((o) => [num(formatDate(o.date)), o.form_slug ?? "—", o.form_type ?? "",
                right(<MoneyText cents={o.amount_total_cents} />), o.payer])} />
          ) : <Text c="dimmed" size="sm">Aucune commande HelloAsso rattachée.</Text>}
          {data.helloasso.items.length > 0 && (
            <SimpleTable head={["Article", "Type", "État", right("Montant"), "Bénéficiaire"]}
              rows={data.helloasso.items.map((it) => [it.name ?? "—",
                <StatusBadge tone={it.type === "Membership" ? "ok" : "neutral"}>{it.type ?? "—"}</StatusBadge>,
                it.state ?? "", right(<MoneyText cents={it.amount_cents} />), it.beneficiary])} />
          )}
          {data.helloasso.payments.length > 0 && (
            <SimpleTable head={["Date", "Moyen", "État", right("Montant")]}
              rows={data.helloasso.payments.map((p) => [num(formatDate(p.date)), p.means ?? "—", p.state ?? "",
                right(<MoneyText cents={p.amount_cents} />)])} />
          )}
        </Section>
      )}

      <FormDrawer opened={editing} onClose={() => setEditing(false)} title={`Modifier ${e.name}`}>
        <EntityForm entity={e} meta={data.meta} onDone={() => setEditing(false)} />
      </FormDrawer>
    </>
  );
}
