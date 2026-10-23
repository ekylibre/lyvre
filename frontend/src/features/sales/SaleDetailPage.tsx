// Ventes › Facture ou avoir (/sales/<id>) : client, lignes, totaux et TVA par taux ; brouillon :
// modifier, supprimer, émettre (numéro, écriture VE, PDF Factur-X) ; pièce émise : PDF, envoi par
// email (SMTP, message modifiable), avoir, encaissements (transaction ou saisie, défaire), relance,
// historique des envois et relances.
import { useState } from "react";
import { useParams } from "react-router";
import {
  Alert, Anchor, Button, Center, Checkbox, Grid, Group, List, Loader, Paper, Stack, Table, TagsInput, Text, TextInput, Textarea, Title,
} from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { Can } from "../../components/Can";
import { ConfirmButton } from "../../components/ConfirmButton";
import { FormBody } from "../../components/ApiForm";
import { FormModal } from "../../components/FormModal";
import { useIntegrationGuard } from "../../components/IntegrationRequired";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate, formatDateTime } from "../../lib/format";
import { AppLink, useGoTo } from "../../app/navigation";
import { PaymentForm } from "./PaymentForm";
import { KIND_TITLES, SALES_KEY, STATUS_TONES, VAT_MODE_LABELS, type SaleDetail } from "./types";

const rate = (bp: number) => `${(bp / 100).toLocaleString("fr-FR")} %`;

function SendForm({ sale, onDone, purpose = "send" }: { sale: SaleDetail; onDone: (s: SaleDetail) => void; purpose?: "send" | "reminder" }) {
  const [to, setTo] = useState<string[]>(sale.recipients);
  const [cc, setCc] = useState<string[]>([]);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const send = useAction(() => api.post<{ item: SaleDetail; notices: Notice[] }>(
    `/api/v1/sales/${sale.id}/${purpose === "reminder" ? "remind" : "send"}`, { to, cc, subject, body }), { invalidate: [SALES_KEY] });
  return (
    <form onSubmit={(e) => { e.preventDefault(); send.mutate(undefined, { onSuccess: (r) => onDone(r.item) }); }}>
      <FormBody submitLabel={purpose === "reminder" ? "Envoyer la relance" : "Envoyer"} onCancel={() => onDone(sale)} loading={send.isPending}>
        <TagsInput label="Destinataires" required value={to} onChange={setTo} description="Email du client (fiche du tiers) ; Entrée pour ajouter une adresse." />
        <TagsInput label="Copie" value={cc} onChange={setCc} />
        <TextInput label="Objet" placeholder="Objet par défaut (Configuration › Structure › Facturation)" value={subject} onChange={(e) => setSubject(e.currentTarget.value)} />
        <Textarea label="Message" placeholder={purpose === "reminder" ? "Message de relance par défaut (restant dû, échéance)" : "Message par défaut"}
          autosize minRows={4} value={body} onChange={(e) => setBody(e.currentTarget.value)} />
        <Text size="sm" c="dimmed">Le PDF de la pièce est joint.</Text>
      </FormBody>
    </form>
  );
}

function CreditForm({ sale, onDone }: { sale: SaleDetail; onDone: (id?: number) => void }) {
  const [reason, setReason] = useState("");
  const [lines, setLines] = useState<number[]>(sale.lines.map((l) => l.id));
  const create = useAction(() => api.post<{ item: SaleDetail; notices: Notice[] }>(`/api/v1/sales/${sale.id}/credit-note`, { reason, line_ids: lines }),
    { invalidate: [SALES_KEY] });
  return (
    <form onSubmit={(e) => { e.preventDefault(); create.mutate(undefined, { onSuccess: (r) => onDone(r.item.id) }); }}>
      <FormBody submitLabel="Créer le brouillon d'avoir" onCancel={() => onDone()} loading={create.isPending}>
        <TextInput label="Motif" required data-autofocus value={reason} onChange={(e) => setReason(e.currentTarget.value)}
          placeholder="Erreur de facturation, remise accordée, annulation…" />
        <Checkbox.Group label="Lignes à créditer" value={lines.map(String)} onChange={(v) => setLines(v.map(Number))}>
          <Stack gap={4} mt={6}>{sale.lines.map((l) => <Checkbox key={l.id} value={String(l.id)}
            label={<>{l.label} — <MoneyText cents={l.total_cents} size="sm" /></>} />)}</Stack>
        </Checkbox.Group>
        <Text size="sm" c="dimmed">Reste créditable : <MoneyText cents={sale.remaining_credit_cents} size="sm" />. Les montants restent modifiables sur le brouillon.</Text>
      </FormBody>
    </form>
  );
}

export default function SaleDetailPage() {
  const id = Number(useParams().sale_id);
  const client = useQueryClient();
  const goTo = useGoTo();
  const key = [...SALES_KEY, id];
  const { data, error } = useQuery({ queryKey: key, retry: false, queryFn: () => api.get<{ item: SaleDetail }>(`/api/v1/sales/${id}`) });
  const [modal, setModal] = useState<"send" | "credit" | "pay" | "remind" | null>(null);
  const smtp = useIntegrationGuard("smtp", "L'envoi par email");
  const refresh = (item: SaleDetail) => { client.setQueryData(key, { item }); void client.invalidateQueries({ queryKey: SALES_KEY }); };
  const issue = useAction(() => api.post<{ item: SaleDetail; notices: Notice[] }>(`/api/v1/sales/${id}/issue`));
  const remove = useAction(() => api.delete<{ notices: Notice[] }>(`/api/v1/sales/${id}`), { invalidate: [SALES_KEY] });
  const quoteStatus = useAction((status: string) => api.post<{ item: SaleDetail; notices: Notice[] }>(`/api/v1/sales/${id}/quote-status`, { status }),
    { invalidate: [SALES_KEY] });
  const toInvoice = useAction(() => api.post<{ item: SaleDetail; notices: Notice[] }>(`/api/v1/sales/${id}/to-invoice`), { invalidate: [SALES_KEY] });
  const rentReceipt = useAction(() => api.post<{ item: { pdf_url: string }; notices: Notice[] }>(`/api/v1/sales/${id}/rent-receipt`),
    { invalidate: [SALES_KEY] });
  const unpay = useAction((paymentId: number) => api.delete<{ item: SaleDetail; notices: Notice[] }>(`/api/v1/sale-payments/${paymentId}`));

  if (error) return <Alert color="brique" mt="md">{(error as Error).message}</Alert>;
  if (!data) return <Center h={300}><Loader /></Center>;
  const s = data.item;
  const draft = s.status === "draft";
  const quote = s.kind === "quote";
  const title = `${KIND_TITLES[s.kind]} ${s.number ?? "brouillon"}`;
  return (
    <>
      <PageHeader title={title}
        description={<Group component="span" gap={8}>
          <StatusBadge tone={STATUS_TONES[s.status]}>{s.status_label}</StatusBadge>
          {s.overdue && <StatusBadge tone="gap">échue</StatusBadge>}
          <Anchor component={AppLink} href={`/entities/${s.client.id}`} size="sm">{s.client.name}</Anchor>
          {s.invoice && <span>sur la facture <Anchor component={AppLink} href={`/sales/${s.invoice.id}`} size="sm">{s.invoice.number}</Anchor></span>}
          {s.lease && <span>bail <Anchor component={AppLink} href={`/leases/${s.lease.id}`} size="sm">{s.lease.unit_label}</Anchor></span>}
          {s.quote && <span>du devis <Anchor component={AppLink} href={`/sales/${s.quote.id}`} size="sm">{s.quote.number}</Anchor></span>}
          {quote && s.validity_date && <span>valable jusqu'au {formatDate(s.validity_date)}</span>}
          {(s.qonto_emit || s.source === "qonto") && <StatusBadge tone="info">{s.source === "qonto" ? "Créée dans Qonto" : "Qonto"}</StatusBadge>}
          {s.qonto_status && <span>Qonto : {s.qonto_status}</span>}
        </Group>}
        actions={<>
          <Can>
            {draft && <Button variant="default" component={AppLink} href={`/sales/${id}/edit`}>Modifier</Button>}
            {draft && <ConfirmButton title={`Supprimer ce brouillon ?`} confirmLabel="Supprimer" loading={remove.isPending}
              onConfirm={() => remove.mutate(undefined, { onSuccess: () => goTo(quote ? "/sales/?kind=quote" : "/sales/") })}>Supprimer</ConfirmButton>}
            {draft && <ConfirmButton danger={false} disabled={s.issue_problems.length > 0} loading={issue.isPending}
              title={`Émettre ${s.kind === "credit_note" ? "l'avoir" : quote ? "le devis" : "la facture"} ?`} confirmLabel="Émettre"
              message={quote ? "Un numéro définitif est attribué et le PDF est produit. Le devis ne pourra plus être modifié."
                : "Un numéro définitif est attribué, l'écriture comptable est passée et le PDF Factur-X est produit. La pièce ne pourra plus être modifiée ni supprimée (on la corrige par un avoir)."}
              onConfirm={() => issue.mutate(undefined, { onSuccess: (r) => refresh(r.item) })}>Émettre</ConfirmButton>}
            {s.kind === "invoice" && s.due_cents > 0 && <Button onClick={() => setModal("pay")}>Encaisser</Button>}
            {!draft && <Button variant="default" onClick={smtp.guard(() => setModal("send"))}>Envoyer</Button>}
            {s.lease && s.paid_cents > 0 && <Button variant="default" loading={rentReceipt.isPending}
              onClick={() => rentReceipt.mutate(undefined, { onSuccess: (r) => { window.open(r.item.pdf_url, "_blank"); void client.invalidateQueries({ queryKey: key }); } })}>
              {s.status === "paid" ? "Quittance" : "Reçu"}</Button>}
            {s.kind === "invoice" && s.overdue && s.due_cents > 0 &&
              <Button variant="default" onClick={smtp.guard(() => setModal("remind"))}>Relancer</Button>}
            {!draft && s.kind === "invoice" && s.status !== "canceled" && s.remaining_credit_cents > 0 &&
              <Button variant="default" onClick={() => setModal("credit")}>Avoir</Button>}
            {quote && ["issued", "expired", "refused"].includes(s.status) &&
              <Button variant="default" loading={quoteStatus.isPending} onClick={() => quoteStatus.mutate("accepted", { onSuccess: (r) => refresh(r.item) })}>Accepté</Button>}
            {quote && ["issued", "expired", "accepted"].includes(s.status) &&
              <Button variant="default" loading={quoteStatus.isPending} onClick={() => quoteStatus.mutate("refused", { onSuccess: (r) => refresh(r.item) })}>Refusé</Button>}
            {quote && ["issued", "expired", "accepted", "invoiced"].includes(s.status) &&
              <Button loading={toInvoice.isPending} onClick={() => toInvoice.mutate(undefined, { onSuccess: (r) => goTo(`/sales/${r.item.id}`) })}>
                {s.status === "invoiced" ? "Nouvelle facture" : "Transformer en facture"}</Button>}
          </Can>
          <Button variant="default" component="a" href={s.pdf_url} target="_blank">{draft ? "Aperçu PDF" : "PDF"}</Button>
          <Button variant="default" component={AppLink} href={quote ? "/sales/?kind=quote" : "/sales/"}>{quote ? "Devis" : "Ventes"}</Button>
        </>} />

      {draft && s.issue_problems.length > 0 && (
        <Alert color="paille" mb="md" title="À compléter avant l'émission :">
          <List size="sm">{s.issue_problems.map((p) => <List.Item key={p}>{p}</List.Item>)}</List>
        </Alert>
      )}
      {s.qonto_error && <Alert color="brique" mb="md" title="Qonto">{s.qonto_error}</Alert>}
      {draft && s.qonto_emit && <Alert color="ardoise" mb="md">À l'émission, la pièce est créée dans Qonto, qui lui donne son numéro et son PDF.</Alert>}
      {s.credit_reason && <Alert color="ardoise" mb="md">Motif de l'avoir : {s.credit_reason}</Alert>}

      <Grid mb="md">
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Paper p="md">
            <Text size="sm" c="dimmed">Client</Text>
            <Text fw={600}>{s.client.name}</Text>
            <Text size="sm">{s.client.address_line1}{s.client.address_line2 && <><br />{s.client.address_line2}</>}<br />
              {s.client.postal_code} {s.client.city}</Text>
            {s.client.siren && <Text size="sm">SIREN {s.client.siren}</Text>}
            {s.client.email && <Text size="sm" c="dimmed">{s.client.email}</Text>}
          </Paper>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Paper p="md">
            <Group gap="xl">
              <div><Text size="sm" c="dimmed">Date</Text><Text className="lv-num">{formatDate(s.issue_date)}</Text></div>
              {s.kind === "invoice" && <div><Text size="sm" c="dimmed">Échéance</Text><Text className="lv-num">{formatDate(s.due_date)}</Text></div>}
              {(s.service_start || s.service_end) && <div><Text size="sm" c="dimmed">Prestation</Text>
                <Text className="lv-num">{formatDate(s.service_start)} – {formatDate(s.service_end)}</Text></div>}
              {s.journal_entry && <div><Text size="sm" c="dimmed">Écriture</Text>
                <Anchor component={AppLink} href={`/entries/${s.journal_entry.id}`} className="lv-num">{s.journal_entry.reference}</Anchor></div>}
              {s.sent_at && <div><Text size="sm" c="dimmed">Envoyée</Text><Text className="lv-num">{formatDate(s.sent_at)}</Text></div>}
            </Group>
            <Text size="sm" c="dimmed" mt="sm">{s.vat_mode && VAT_MODE_LABELS[s.vat_mode]}</Text>
          </Paper>
        </Grid.Col>
      </Grid>

      <Paper p={0} mb="md">
        <Table.ScrollContainer minWidth={700}>
          <Table>
            <Table.Thead><Table.Tr><Table.Th>Désignation</Table.Th><Table.Th ta="right">Qté</Table.Th><Table.Th ta="right">PU HT</Table.Th>
              <Table.Th ta="right">Remise</Table.Th><Table.Th ta="right">TVA</Table.Th><Table.Th>Compte</Table.Th><Table.Th ta="right">HT</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {s.lines.map((l) => (
                <Table.Tr key={l.id}>
                  <Table.Td>{l.label}{l.description && <Text size="xs" c="dimmed">{l.description}</Text>}</Table.Td>
                  <Table.Td ta="right" className="lv-num">{l.quantity} {l.unit}</Table.Td>
                  <Table.Td ta="right" className="lv-num">{l.unit_price} €</Table.Td>
                  <Table.Td ta="right" className="lv-num">{l.discount ? `${l.discount} %` : ""}</Table.Td>
                  <Table.Td ta="right" className="lv-num">{s.vat_mode === "none" ? "—" : `${l.vat_rate} %`}</Table.Td>
                  <Table.Td className="lv-num">{l.account_code}</Table.Td>
                  <Table.Td ta="right"><MoneyText cents={l.untaxed_cents} size="sm" /></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        <Stack gap={2} align="flex-end" p="md">
          <Text size="sm">Total HT <MoneyText cents={s.untaxed_cents} size="sm" /></Text>
          {s.vat_rows.map((r) => <Text key={r.rate} size="sm">TVA {rate(r.rate)} sur <MoneyText cents={r.base} size="sm" /> : <MoneyText cents={r.tax} size="sm" /></Text>)}
          <Text fw={700}>Total {s.vat_mode === "none" ? "" : "TTC "}<MoneyText cents={s.total_cents} fw={700} /></Text>
        </Stack>
      </Paper>

      {s.kind === "invoice" && !draft && (
        <Paper p="md" mb="md">
          <Group justify="space-between" mb="xs">
            <Title order={3}>Encaissements</Title>
            <Text size="sm">Encaissé <MoneyText cents={s.paid_cents} size="sm" /> · restant dû <MoneyText cents={s.due_cents} size="sm" fw={600} />
              {s.reminder_count > 0 && <Text span size="sm" c="dimmed"> · {s.reminder_count} relance(s), la dernière le {formatDate(s.last_reminder_at)}</Text>}</Text>
          </Group>
          {s.rent_receipts.length > 0 && <Group gap="xs" mb="xs">{s.rent_receipts.map((r) =>
            <Anchor key={r.id} href={r.pdf_url} target="_blank" size="sm">{r.label} (<MoneyText cents={r.paid_cents} size="sm" />)</Anchor>)}</Group>}
          {s.payments.length === 0 ? <Text size="sm" c="dimmed">Aucun encaissement.</Text> : (
            <Table>
              <Table.Tbody>
                {s.payments.map((p) => (
                  <Table.Tr key={p.id}>
                    <Table.Td className="lv-num">{formatDate(p.paid_on)}</Table.Td>
                    <Table.Td>{p.origin === "bank" ? <>Transaction : {p.transaction?.label ?? "—"}</> : <>{p.method} — {p.account}</>}
                      {p.vat_released_cents > 0 && <Text size="xs" c="dimmed">TVA encaissée virée : <MoneyText cents={p.vat_released_cents} size="xs" /></Text>}</Table.Td>
                    <Table.Td>{p.journal_entry && <Anchor component={AppLink} href={`/entries/${p.journal_entry.id}`} size="sm" className="lv-num">{p.journal_entry.reference}</Anchor>}</Table.Td>
                    <Table.Td ta="right"><MoneyText cents={p.amount_cents} size="sm" /></Table.Td>
                    <Table.Td ta="right"><Can><ConfirmButton size="compact-sm" variant="subtle" title="Défaire cet encaissement ?" confirmLabel="Défaire"
                      message="Son écriture est supprimée et la transaction bancaire n'est plus rapprochée (une transaction partagée entre plusieurs factures est défaite pour toutes)."
                      loading={unpay.isPending} onConfirm={() => unpay.mutate(p.id, { onSuccess: (r) => refresh(r.item) })}>Défaire</ConfirmButton></Can></Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </Paper>
      )}

      {quote && s.invoices.length > 0 && (
        <Paper p="md" mb="md">
          <Title order={3} mb="xs">Factures du devis</Title>
          {s.invoices.map((i) => <Group key={i.id} gap="xs"><Anchor component={AppLink} href={`/sales/${i.id}`}>{i.number ?? "brouillon"}</Anchor>
            <StatusBadge tone={STATUS_TONES[i.status]}>{i.status === "draft" ? "Brouillon" : "Émise"}</StatusBadge><MoneyText cents={i.total_cents} size="sm" /></Group>)}
        </Paper>
      )}

      {(s.credit_notes.length > 0 || s.emails.length > 0) && (
        <Grid>
          {s.credit_notes.length > 0 && <Grid.Col span={{ base: 12, md: 6 }}><Paper p="md">
            <Title order={3} mb="xs">Avoirs</Title>
            {s.credit_notes.map((c) => <Group key={c.id} gap="xs"><Anchor component={AppLink} href={`/sales/${c.id}`}>{c.number ?? "brouillon"}</Anchor>
              <StatusBadge tone={STATUS_TONES[c.status]}>{c.status === "draft" ? "Brouillon" : "Émis"}</StatusBadge><MoneyText cents={c.total_cents} size="sm" /></Group>)}
          </Paper></Grid.Col>}
          {s.emails.length > 0 && <Grid.Col span={{ base: 12, md: 6 }}><Paper p="md">
            <Title order={3} mb="xs">Envois</Title>
            {s.emails.map((e) => <Text key={e.sent_at + e.recipients} size="sm" c={e.status === "failed" ? "var(--lv-brique)" : undefined}>
              {formatDateTime(e.sent_at)} — {e.purpose === "reminder" ? "relance — " : ""}{e.recipients}{e.status === "failed" && ` : échec (${e.error})`}</Text>)}
          </Paper></Grid.Col>}
        </Grid>
      )}

      <FormModal opened={modal === "send"} onClose={() => setModal(null)} title={`Envoyer ${title}`} size="lg">
        {modal === "send" && <SendForm sale={s} onDone={(item) => { refresh(item); setModal(null); }} />}
      </FormModal>
      <FormModal opened={modal === "remind"} onClose={() => setModal(null)} title={`Relancer ${title}`} size="lg">
        {modal === "remind" && <SendForm sale={s} purpose="reminder" onDone={(item) => { refresh(item); setModal(null); }} />}
      </FormModal>
      <FormModal opened={modal === "pay"} onClose={() => setModal(null)} title={`Encaisser ${title}`} size="lg">
        {modal === "pay" && <PaymentForm sale={s} onDone={(item) => { if (item) refresh(item); setModal(null); }} />}
      </FormModal>
      <FormModal opened={modal === "credit"} onClose={() => setModal(null)} title={`Avoir sur la facture ${s.number}`}>
        {modal === "credit" && <CreditForm sale={s} onDone={(noteId) => { setModal(null); if (noteId) goTo(`/sales/${noteId}`); }} />}
      </FormModal>
    </>
  );
}
