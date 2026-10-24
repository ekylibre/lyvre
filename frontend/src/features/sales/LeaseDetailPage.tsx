// Ventes › Bail : locataire, biens loués (lignes A, B…), loyer annuel et échéance, charges, dépôt de
// garantie (encaissement au compte 165), avis d'échéance (factures) et quittances / reçus (PDF, envoi
// au locataire). « Modifier » rouvre l'assistant.
import { useState } from "react";
import { useParams } from "react-router";
import { Alert, Anchor, Button, Center, Grid, Group, Loader, Paper, Select, Stack, Table, Text, TextInput, Title } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { FormBody } from "../../components/ApiForm";
import { Can } from "../../components/Can";
import { confirmAction } from "../../components/ConfirmButton";
import { FormModal } from "../../components/FormModal";
import { HtmlTemplateEditor } from "../../components/HtmlTemplateEditor";
import { useIntegrationGuard } from "../../components/IntegrationRequired";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import type { LeasesMeta } from "./LeaseWizardPage";
import { LEASES_KEY, STATUS_TONES, type Lease } from "./types";

function DepositForm({ lease, accounts, onDone }: { lease: Lease; accounts: LeasesMeta["bank_accounts"]; onDone: (item?: Lease) => void }) {
  const [paidOn, setPaidOn] = useState(new Date().toISOString().slice(0, 10));
  const [account, setAccount] = useState<string | null>(accounts[0]?.value ?? null);
  const save = useAction(() => api.post<{ item: Lease; notices: Notice[] }>(`/api/v1/leases/${lease.id}/deposit`, { paid_on: paidOn, bank_account_id: account }));
  return (
    <form onSubmit={(e) => { e.preventDefault(); save.mutate(undefined, { onSuccess: (r) => onDone(r.item) }); }}>
      <FormBody submitLabel="Encaisser le dépôt" onCancel={() => onDone()} loading={save.isPending}>
        <Text size="sm">Dépôt de garantie : <MoneyText cents={lease.deposit_cents} fw={600} /> — banque ou caisse au débit, 165 au crédit.</Text>
        <Group grow>
          <TextInput label="Date" type="date" value={paidOn} onChange={(e) => setPaidOn(e.currentTarget.value)} />
          <Select label="Encaissé sur" data={accounts} value={account} onChange={setAccount} allowDeselect={false} />
        </Group>
      </FormBody>
    </form>
  );
}

/** Retouche du texte d'un bail (pour ce bail seul). */
function DocumentForm({ lease, onDone }: { lease: Lease; onDone: (item?: Lease) => void }) {
  const { data } = useQuery({ queryKey: [...LEASES_KEY, lease.id, "document"], gcTime: 0,
    queryFn: () => api.get<{ item: { body_html: string } }>(`/api/v1/leases/${lease.id}/document`) });
  const [body, setBody] = useState<string | null>(null);
  const save = useAction(() => api.put<{ item: Lease; notices: Notice[] }>(`/api/v1/leases/${lease.id}/document`, { body_html: body }));
  if (!data) return <Center h={200}><Loader /></Center>;
  return (
    <form onSubmit={(e) => { e.preventDefault(); save.mutate(undefined, { onSuccess: (r) => onDone(r.item) }); }}>
      <FormBody submitLabel="Enregistrer le texte" onCancel={() => onDone()} loading={save.isPending}>
        <Text size="sm" c="dimmed">La retouche ne vaut que pour ce bail ; le modèle ne change pas.</Text>
        <HtmlTemplateEditor label="Source du texte du bail" initial={data.item.body_html} onChange={setBody} />
      </FormBody>
    </form>
  );
}

const SIGNER_TONES: Record<string, "ok" | "todo" | "gap" | "neutral" | "info"> = {
  completed: "ok", declined: "gap", sent: "info", opened: "info", awaiting: "neutral" };

/** Signature électronique (lot L4) : signataires prévus, envoi, suivi, PDF signé. */
function SignaturePanel({ lease, onChange }: { lease: Lease; onChange: (item: Lease) => void }) {
  const signing = useIntegrationGuard("documenso", "L'envoi à la signature");
  const send = useAction(() => api.post<{ item: Lease; notices: Notice[] }>(`/api/v1/leases/${lease.id}/signature`));
  const refresh = useAction(() => api.post<{ item: Lease; notices: Notice[] }>(`/api/v1/leases/${lease.id}/signature/refresh`));
  const cancel = useAction(() => api.delete<{ item: Lease; notices: Notice[] }>(`/api/v1/leases/${lease.id}/signature`));
  const sig = lease.signature;
  const sending = !sig || sig.status === "declined" || sig.status === "expired";
  if (lease.status !== "active" || !lease.kind) return null;
  return (
    <Paper p="md" mb="md">
      <Group justify="space-between" align="flex-start" mb="xs">
        <div>
          <Title order={3} mb={4}>Signature</Title>
          {sig ? <Group gap={8}><StatusBadge tone={sig.status === "completed" ? "ok" : sig.status === "sent" ? "info" : "gap"}>{sig.status_label}</StatusBadge>
            <Text size="sm" c="dimmed">envoyé le {formatDate(sig.sent_at)}{sig.completed_at ? `, signé le ${formatDate(sig.completed_at)}` : ""}</Text></Group>
            : <Text size="sm" c="dimmed">Signature électronique avec Documenso : les gérants signent, puis le preneur.</Text>}
        </div>
        <Group gap="xs">
          {sig?.files.signed && <Button component="a" href={sig.files.signed} target="_blank">PDF signé</Button>}
          {sig?.files.audit && <Button variant="default" component="a" href={sig.files.audit} target="_blank">Journal d'audit</Button>}
          {sig?.files.sent && !sig.files.signed && <Button variant="default" component="a" href={sig.files.sent} target="_blank">PDF envoyé</Button>}
          <Can>
            {sig?.status === "sent" && <>
              <Button variant="default" loading={refresh.isPending} onClick={signing.guard(() => refresh.mutate(undefined, { onSuccess: (r) => onChange(r.item) }))}>Actualiser</Button>
              <Button variant="subtle" color="brique" onClick={signing.guard(() => confirmAction({
                title: "Annuler l'envoi à la signature ?", confirmLabel: "Annuler l'envoi",
                message: "L'envoi est annulé chez Documenso (les signataires sont prévenus) ; le bail redevient modifiable.",
                onConfirm: () => cancel.mutate(undefined, { onSuccess: (r) => onChange(r.item) }) }))}>Annuler l'envoi</Button>
            </>}
            {sending && <Button disabled={!!lease.signature_problems?.length} loading={send.isPending}
              onClick={signing.guard(() => confirmAction({
                title: "Envoyer le bail à la signature ?", danger: false, confirmLabel: "Envoyer",
                message: `Documenso envoie une invitation par e-mail à ${(lease.signers_planned ?? []).map((s) => `${s.name} (${s.email})`).join(", puis ")}. Le bail ne sera plus modifiable, sauf en annulant l'envoi.`,
                onConfirm: () => send.mutate(undefined, { onSuccess: (r) => onChange(r.item) }) }))}>
              {sig ? "Renvoyer à la signature" : "Envoyer à la signature"}</Button>}
          </Can>
        </Group>
      </Group>
      {sig?.error && <Alert color="brique" variant="light" mb="xs">{sig.error}</Alert>}
      {sending && !!lease.signature_problems?.length && (
        <Alert color="paille" variant="light" mb="xs" title="Envoi impossible">{lease.signature_problems.join(" ")}</Alert>
      )}
      <Table>
        <Table.Tbody>{(sig?.signers ?? (lease.signers_planned ?? []).map((s) => ({ ...s, status: "", status_label: "", signed_at: null, declined_at: null }))).map((s) => (
          <Table.Tr key={s.role}>
            <Table.Td fw={600}>{s.role}</Table.Td><Table.Td>{s.name}</Table.Td><Table.Td>{s.email || "—"}</Table.Td>
            <Table.Td>{s.status && <StatusBadge tone={SIGNER_TONES[s.status] ?? "neutral"}>{s.status_label}</StatusBadge>}
              {s.signed_at && <Text span size="xs" c="dimmed"> le {formatDate(s.signed_at)}</Text>}</Table.Td>
          </Table.Tr>))}</Table.Tbody>
      </Table>
    </Paper>
  );
}

export default function LeaseDetailPage() {
  const id = Number(useParams().lease_id);
  const client = useQueryClient();
  const key = [...LEASES_KEY, id];
  const { data } = useQuery({ queryKey: key, queryFn: () => api.get<{ item: Lease }>(`/api/v1/leases/${id}`) });
  const meta = useList<Lease, LeasesMeta>(LEASES_KEY, "/api/v1/leases").data?.meta;
  const [modal, setModal] = useState<"deposit" | "document" | null>(null);
  const regenerate = useAction(() => api.post<{ item: Lease; notices: Notice[] }>(`/api/v1/leases/${id}/document/regenerate`));
  const smtp = useIntegrationGuard("smtp", "L'envoi par email");
  const sendReceipt = useAction((receiptId: number) => api.post<{ notices: Notice[] }>(`/api/v1/rent-receipts/${receiptId}/send`, {}),
    { invalidate: [LEASES_KEY] });
  if (!data) return <Center h={300}><Loader /></Center>;
  const l = data.item;
  const refresh = (item?: Lease) => { if (item) client.setQueryData(key, { item }); void client.invalidateQueries({ queryKey: LEASES_KEY }); setModal(null); };
  return (
    <>
      <PageHeader title={l.unit_label}
        description={<Group component="span" gap={8}>{l.status === "draft" ? <StatusBadge tone="todo">Brouillon</StatusBadge>
          : <StatusBadge tone={l.active ? "ok" : "neutral"}>{l.active ? "En cours" : "Terminé"}</StatusBadge>}
          {l.kind_label && <Text span size="sm">{l.kind_label}</Text>}
          <Anchor component={AppLink} href={`/entities/${l.tenant.id}`} size="sm">{l.tenant.name}</Anchor></Group>}
        actions={<>
          <Can>
            {l.status === "active" && l.deposit_cents > 0 && !l.deposit_entry && <Button variant="default" onClick={() => setModal("deposit")}>Encaisser le dépôt</Button>}
            {!l.locked && <Button variant="default" component={AppLink} href={`/leases/${l.id}/edit`}>Modifier</Button>}
          </Can>
          <Button variant="default" component={AppLink} href="/leases/">Baux</Button>
        </>} />
      <Grid mb="md">
        <Grid.Col span={{ base: 12, md: 6 }}><Paper p="md">
          <Text size="sm" c="dimmed">Biens</Text>
          <Text>{l.premises_label && <>{l.premises_label}<br /></>}{l.address_line1} {l.address_line2}<br />{l.postal_code} {l.city}</Text>
          <Text size="sm" mt="xs">Du {formatDate(l.start_date)}{l.end_date ? ` au ${formatDate(l.end_date)}` : ""} · échéance le {l.due_day} ({l.in_advance ? "à échoir" : "échu"})</Text>
        </Paper></Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}><Paper p="md">
          <Group gap="xl">
            <div><Text size="sm" c="dimmed">Loyer annuel</Text><MoneyText cents={l.annual_cents} /></div>
            <div><Text size="sm" c="dimmed">Échéance</Text><MoneyText cents={l.rent_cents} /></div>
            <div><Text size="sm" c="dimmed">Charges</Text><MoneyText cents={l.charges_cents} /></div>
            <div><Text size="sm" c="dimmed">Dépôt de garantie</Text><MoneyText cents={l.deposit_cents} />
              {l.deposit_entry && <Text size="xs"><Anchor component={AppLink} href={`/entries/${l.deposit_entry.id}`}>{l.deposit_entry.reference}</Anchor></Text>}</div>
            <div><Text size="sm" c="dimmed">Prochaine échéance</Text><Text className="lv-num">{formatDate(l.next_date)}</Text></div>
          </Group>
        </Paper></Grid.Col>
      </Grid>
      {!!l.items?.length && (
        <Paper p="md" mb="md">
          <Title order={3} mb="xs">Biens loués</Title>
          <Table>
            <Table.Thead><Table.Tr>
              <Table.Th>Lettre</Table.Th><Table.Th>Désignation</Table.Th><Table.Th ta="right">Surface</Table.Th>
              <Table.Th ta="right">Dont bâti</Table.Th><Table.Th>Cadastre</Table.Th><Table.Th ta="right">Montant annuel</Table.Th>
            </Table.Tr></Table.Thead>
            <Table.Tbody>{l.items.map((i) => (
              <Table.Tr key={i.id}>
                <Table.Td fw={600}>{i.letter}</Table.Td>
                <Table.Td>{i.label}{i.partial && <Text span size="xs" c="dimmed"> (partie)</Text>}</Table.Td>
                <Table.Td ta="right" className="lv-num">{i.area_m2 ? `${i.area_m2.toLocaleString("fr-FR")} m²` : "—"}</Table.Td>
                <Table.Td ta="right" className="lv-num">{i.built_m2 ? `${i.built_m2.toLocaleString("fr-FR")} m²` : "—"}</Table.Td>
                <Table.Td>{i.cadastral_refs.join(", ")}</Table.Td>
                <Table.Td ta="right"><MoneyText cents={i.annual_cents} size="sm" /></Table.Td>
              </Table.Tr>))}</Table.Tbody>
          </Table>
        </Paper>
      )}
      <Paper p="md" mb="md">
        <Group justify="space-between" align="flex-start">
          <div>
            <Title order={3} mb={4}>Texte du bail</Title>
            <Text size="sm" c="dimmed">{!l.kind ? "Choisissez le type du bail (Modifier) pour rédiger son texte."
              : l.document.frozen ? `Rédigé le ${formatDate(l.document.generated_at)}${l.document.edited ? ", retouché pour ce bail" : ""}.`
                : "Brouillon : le texte est rédigé depuis le modèle à la validation."}</Text>
          </div>
          {l.kind && <Group gap="xs">
            <Button variant="default" component="a" href={l.document.preview_url} target="_blank">Aperçu (PDF)</Button>
            <Can>
              {!l.locked && <Button variant="default" onClick={() => setModal("document")}>Retoucher</Button>}
              {l.document.frozen && !l.locked && <Button variant="subtle" onClick={() => confirmAction({
                title: "Régénérer le texte depuis le modèle ?", confirmLabel: "Régénérer",
                message: "Le texte est rédigé à nouveau avec le modèle et les données actuelles du bail ; les retouches sont perdues.",
                onConfirm: () => regenerate.mutate(undefined, { onSuccess: (r) => refresh(r.item) }) })}>Régénérer</Button>}
            </Can>
          </Group>}
        </Group>
      </Paper>
      <SignaturePanel lease={l} onChange={(item) => refresh(item)} />
      <Grid>
        <Grid.Col span={{ base: 12, lg: 7 }}><Paper p="md">
          <Title order={3} mb="xs">Avis d'échéance</Title>
          {!l.invoices?.length ? <Text size="sm" c="dimmed">Aucun : ils sont préparés dans « À émettre » à chaque échéance.</Text> : (
            <Table><Table.Tbody>{l.invoices.map((s) => (
              <Table.Tr key={s.id}>
                <Table.Td><Anchor component={AppLink} href={`/sales/${s.id}`} size="sm" className="lv-num">{s.number ?? "brouillon"}</Anchor></Table.Td>
                <Table.Td className="lv-num">{formatDate(s.service_start)} – {formatDate(s.service_end)}</Table.Td>
                <Table.Td ta="right"><MoneyText cents={s.total_cents} size="sm" /></Table.Td>
                <Table.Td><StatusBadge tone={STATUS_TONES[s.status]}>{s.status_label}</StatusBadge></Table.Td>
              </Table.Tr>))}</Table.Tbody></Table>
          )}
        </Paper></Grid.Col>
        <Grid.Col span={{ base: 12, lg: 5 }}><Paper p="md">
          <Title order={3} mb="xs">Quittances et reçus</Title>
          {!l.receipts?.length ? <Text size="sm" c="dimmed">Produits depuis l'avis d'échéance payé (bouton « Quittance »).</Text> : (
            <Stack gap={6}>{l.receipts.map((r) => (
              <Group key={r.id} justify="space-between" gap="xs">
                <Text size="sm">{r.label} {formatDate(r.period_start)} – {formatDate(r.period_end)} · <MoneyText cents={r.paid_cents} size="sm" />
                  {r.sent_at && <Text span size="xs" c="dimmed"> · envoyée le {formatDate(r.sent_at)}</Text>}</Text>
                <Group gap={4}>
                  <Button size="compact-sm" variant="subtle" component="a" href={r.pdf_url} target="_blank">PDF</Button>
                  <Can><Button size="compact-sm" variant="subtle" loading={sendReceipt.isPending}
                    onClick={smtp.guard(() => sendReceipt.mutate(r.id))}>Envoyer</Button></Can>
                </Group>
              </Group>))}</Stack>
          )}
        </Paper></Grid.Col>
      </Grid>
      {l.notes && <Alert color="ardoise" mt="md">{l.notes}</Alert>}
      <FormModal opened={modal === "document"} onClose={() => setModal(null)} title={`Texte du bail ${l.unit_label}`} size="90%">
        {modal === "document" && <DocumentForm lease={l} onDone={refresh} />}
      </FormModal>
      <FormModal opened={modal === "deposit"} onClose={() => setModal(null)} title="Dépôt de garantie">
        {modal === "deposit" && meta && <DepositForm lease={l} accounts={meta.bank_accounts} onDone={refresh} />}
      </FormModal>
    </>
  );
}
