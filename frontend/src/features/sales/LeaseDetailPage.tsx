// Ventes › Bail : locataire, lot, loyer et charges, échéancier, dépôt de garantie (encaissement au
// compte 165), avis d'échéance (factures) et quittances / reçus (PDF, envoi au locataire).
import { useState } from "react";
import { useParams } from "react-router";
import { Alert, Anchor, Button, Center, Grid, Group, Loader, Paper, Select, Stack, Table, Text, TextInput, Title } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { FormBody } from "../../components/ApiForm";
import { Can } from "../../components/Can";
import { FormModal } from "../../components/FormModal";
import { useIntegrationGuard } from "../../components/IntegrationRequired";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { LeaseForm, type LeasesMeta } from "./LeasesPage";
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

export default function LeaseDetailPage() {
  const id = Number(useParams().lease_id);
  const client = useQueryClient();
  const key = [...LEASES_KEY, id];
  const { data } = useQuery({ queryKey: key, queryFn: () => api.get<{ item: Lease }>(`/api/v1/leases/${id}`) });
  const meta = useList<Lease, LeasesMeta>(LEASES_KEY, "/api/v1/leases").data?.meta;
  const [modal, setModal] = useState<"edit" | "deposit" | null>(null);
  const smtp = useIntegrationGuard("smtp", "L'envoi par email");
  const sendReceipt = useAction((receiptId: number) => api.post<{ notices: Notice[] }>(`/api/v1/rent-receipts/${receiptId}/send`, {}),
    { invalidate: [LEASES_KEY] });
  if (!data) return <Center h={300}><Loader /></Center>;
  const l = data.item;
  const refresh = (item?: Lease) => { if (item) client.setQueryData(key, { item }); void client.invalidateQueries({ queryKey: LEASES_KEY }); setModal(null); };
  return (
    <>
      <PageHeader title={l.unit_label}
        description={<Group component="span" gap={8}><StatusBadge tone={l.active ? "ok" : "neutral"}>{l.active ? "En cours" : "Terminé"}</StatusBadge>
          <Anchor component={AppLink} href={`/entities/${l.tenant.id}`} size="sm">{l.tenant.name}</Anchor></Group>}
        actions={<>
          <Can>
            {l.deposit_cents > 0 && !l.deposit_entry && <Button variant="default" onClick={() => setModal("deposit")}>Encaisser le dépôt</Button>}
            <Button variant="default" onClick={() => setModal("edit")}>Modifier</Button>
          </Can>
          <Button variant="default" component={AppLink} href="/leases/">Baux</Button>
        </>} />
      <Grid mb="md">
        <Grid.Col span={{ base: 12, md: 6 }}><Paper p="md">
          <Text size="sm" c="dimmed">Lot</Text>
          <Text>{l.address_line1} {l.address_line2}<br />{l.postal_code} {l.city}</Text>
          <Text size="sm" mt="xs">Du {formatDate(l.start_date)}{l.end_date ? ` au ${formatDate(l.end_date)}` : ""} · échéance le {l.due_day} ({l.in_advance ? "à échoir" : "échu"})</Text>
        </Paper></Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}><Paper p="md">
          <Group gap="xl">
            <div><Text size="sm" c="dimmed">Loyer</Text><MoneyText cents={l.rent_cents} /></div>
            <div><Text size="sm" c="dimmed">Charges</Text><MoneyText cents={l.charges_cents} /></div>
            <div><Text size="sm" c="dimmed">Dépôt de garantie</Text><MoneyText cents={l.deposit_cents} />
              {l.deposit_entry && <Text size="xs"><Anchor component={AppLink} href={`/entries/${l.deposit_entry.id}`}>{l.deposit_entry.reference}</Anchor></Text>}</div>
            <div><Text size="sm" c="dimmed">Prochaine échéance</Text><Text className="lv-num">{formatDate(l.next_date)}</Text></div>
          </Group>
        </Paper></Grid.Col>
      </Grid>
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
      <FormModal opened={modal === "edit"} onClose={() => setModal(null)} title={`Modifier ${l.unit_label}`} size="xl">
        {modal === "edit" && meta && <LeaseForm lease={l} meta={meta} onDone={refresh} />}
      </FormModal>
      <FormModal opened={modal === "deposit"} onClose={() => setModal(null)} title="Dépôt de garantie">
        {modal === "deposit" && meta && <DepositForm lease={l} accounts={meta.bank_accounts} onDone={refresh} />}
      </FormModal>
    </>
  );
}
