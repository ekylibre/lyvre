// Achats › Facture : informations, comptabilisation, envoi à Qonto, règlement (transactions de
// même montant proposées), règlements passés, lignes modifiables tant qu'elle n'est pas comptabilisée.
import { useEffect, useState, type ReactNode } from "react";
import { useParams } from "react-router";
import {
  Alert, Anchor, Badge, Button, Center, Code, Collapse, Grid, Group, List, Loader, Paper, Select, Stack, Table, Text, Title,
} from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan, useIntegration } from "../../api/session";
import { ConfirmButton } from "../../components/ConfirmButton";
import { FormModal } from "../../components/FormModal";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { Can } from "../../components/Can";
import { OriginBadge } from "../../components/OriginBadge";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink, useGoTo } from "../../app/navigation";
import { selectedTotal, TransactionPicker } from "../../components/bank/TransactionPicker";
import { AssociatePaymentForm } from "../associates/AssociatePaymentForm";
import { AttachmentPreview } from "./AttachmentPreview";
import { LinesEditor } from "./LinesEditor";
import { EMPTY_LINE } from "./lines";
import { deleteMessage, PAYMENT_TONES, PURCHASES_KEY, STATE_TONES, purchaseTitle, type LineRow, type PurchaseDetail } from "./types";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return <Table.Tr><Table.Th w="28%" fw={500} c="dimmed">{label}</Table.Th><Table.Td>{children}</Table.Td></Table.Tr>;
}

const amount = (cents: number | null) => (cents === null ? "—" : <MoneyText cents={cents} />);

export default function PurchaseDetailPage() {
  const can = useCan();
  const qontoEnabled = useIntegration("qonto", "purchases");
  const id = Number(useParams().purchase_id);
  const goTo = useGoTo();
  // Lot F5 : immobilisation préremplie depuis une ligne au compte 2x.
  const createAsset = useAction((lineId: number) => api.post<{ item: { id: number }; notices: Notice[] }>(
    `/api/v1/purchases/${id}/lines/${lineId}/asset`, {}), { invalidate: [PURCHASES_KEY, ["assets"]] });
  const key = [...PURCHASES_KEY, id];
  const { data, error } = useQuery({ queryKey: key, retry: false,
    queryFn: () => api.get<PurchaseDetail>(`/api/v1/purchases/${id}`) });
  const [rows, setRows] = useState<LineRow[]>([]);
  const [showPreview, setShowPreview] = useState(false);
  useEffect(() => { if (data) setRows(data.lines.length ? data.lines : [EMPTY_LINE]); }, [data]);

  const opts = { invalidate: [PURCHASES_KEY] };
  const post = useAction(() => api.post<{ notices: Notice[] }>(`/api/v1/purchases/${id}/post`), opts);
  const unpost = useAction(() => api.post<{ notices: Notice[] }>(`/api/v1/purchases/${id}/unpost`), opts);
  // Lot AK3 : saisie par clé d'API, vérifiée par l'utilisateur (comptabilisée si elle est prête).
  const check = useAction(() => api.post<{ notices: Notice[] }>(`/api/v1/purchases/${id}/check`), { invalidate: [PURCHASES_KEY, ["dashboard"]] });
  const saveLines = useAction((r: LineRow[]) => api.put<{ notices: Notice[] }>(`/api/v1/purchases/${id}/lines`, { rows: r }), opts);
  const setRegime = useAction((regime: string | null) => api.put<{ notices: Notice[] }>(`/api/v1/purchases/${id}/vat-regime`,
    { vat_regime: regime }), opts);
  const sendToQonto = useAction(() => api.post<{ notices: Notice[] }>(`/api/v1/purchases/${id}/qonto`), opts);
  const link = useAction((ids: number[]) => api.post<{ notices: Notice[] }>(`/api/v1/purchases/${id}/payments`, { bank_transaction_ids: ids }), opts);
  const [picked, setPicked] = useState<number[]>([]);
  const [payingByAssociate, setPayingByAssociate] = useState(false);
  const unlink = useAction((pid: number) => api.delete<{ notices: Notice[] }>(`/api/v1/purchases/${id}/payments/${pid}`), opts);
  const remove = useAction(() => api.delete<{ notices: Notice[] }>(`/api/v1/purchases/${id}`));

  if (error) return <Alert color="brique" mt="md">{(error as Error).message}</Alert>;
  if (!data) return <Center h={300}><Loader /></Center>;
  const p = data.item;
  const editable = p.state.code !== "posted";
  const fromQonto = p.source === "qonto";
  const qonto = qontoEnabled; // désactivée : ni envoi à Qonto, ni « à revoir » (données Qonto conservées)
  const name = `${p.is_credit_note ? "l'avoir" : "la facture"} ${p.invoice_number || "sans numéro"}`;

  return (
    <>
      <PageHeader title={purchaseTitle(p)}
        description={
          <Group component="span" gap={8}>
            <StatusBadge tone={STATE_TONES[p.state.code]}>{p.state.label}</StatusBadge>
            {p.is_einvoice && <Badge size="sm" variant="outline" color="gray">e-facture</Badge>}
            {p.supplier
              ? <span><Anchor component={AppLink} href={`/entities/${p.supplier.id}`} size="sm">{p.supplier.name}</Anchor>
                {p.supplier_account_code && <> · compte <Code>{p.supplier_account_code}</Code></>}</span>
              : <span>{p.supplier_name || "Fournisseur inconnu"} <StatusBadge tone="todo">à rattacher</StatusBadge></span>}
            {p.source === "manual" && <Badge size="sm" variant="outline" color="gray">Saisie</Badge>}
            <OriginBadge origin={p.origin} />
            {(p.in_qonto || fromQonto) && <span>Qonto : {p.qonto_status_label ?? "—"}</span>}
          </Group>
        }
        actions={<>
          <Can>{p.source === "manual" && editable && <Button variant="default" component={AppLink} href={`/purchases/${id}/edit`}>Modifier l'en-tête</Button>}
          <ConfirmButton title={`Supprimer ${name} ?`} confirmLabel="Supprimer" loading={remove.isPending}
            message={deleteMessage(p)}
            onConfirm={() => remove.mutate(undefined, { onSuccess: () => goTo("/purchases/") })}>Supprimer</ConfirmButton></Can>
          <Button variant="default" component={AppLink} href="/purchases/">Retour</Button>
        </>} />

      {qonto && p.review_reason && <Alert color="brique" mb="sm" title="À revoir.">{p.review_reason} Annulez la comptabilisation pour reprendre les données de Qonto.</Alert>}
      {p.origin?.pending && p.state.code !== "posted" && (
        <Alert color="paille" mb="sm" title={`Saisie par « ${p.origin.label} »`}>
          <Group justify="space-between" gap="sm" wrap="nowrap">
            <Text size="sm">Vérifiez le fournisseur, les montants et les lignes (modifiez-les au besoin), puis marquez la facture
              vérifiée : elle sera comptabilisée si elle est complète.{p.origin.external_ref && <> Référence : <Code>{p.origin.external_ref}</Code>.</>}</Text>
            <Can><Button loading={check.isPending} onClick={() => check.mutate()}>Marquer vérifiée</Button></Can>
          </Group>
        </Alert>
      )}
      {p.state.reasons.length > 0 && (
        <Alert color="paille" mb="sm" title="À compléter avant comptabilisation :">
          <List size="sm">{p.state.reasons.map((r) => <List.Item key={r}>{r}</List.Item>)}</List>
        </Alert>
      )}

      <Grid mb="md">
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Paper p="xs">
            <Table>
              <Table.Tbody>
                <Row label="Date"><span className="lv-num">{formatDate(p.issue_date)}</span>
                  {data.fiscal_year && <Text span size="sm" c="dimmed"> · exercice {data.fiscal_year.label}, {data.fiscal_year.vat_liable ? "soumis" : "non soumis"} à la TVA</Text>}</Row>
                <Row label="Échéance"><span className="lv-num">{formatDate(p.due_date)}</span></Row>
                <Row label="Paiement"><span className="lv-num">{formatDate(p.payment_date)}</span></Row>
                <Row label={fromQonto ? "Montants Qonto" : "Montants"}>
                  HT {amount(p.untaxed_cents)} · TVA {amount(p.tax_cents)} · <b>TTC <MoneyText cents={p.total_cents} fw={700} /></b></Row>
                {data.fiscal_year?.vat_liable && p.effective_vat_regime && (
                  <Row label="Régime TVA">
                    {p.journal_entry_id || !can.write
                      ? <Text size="sm">{data.meta.vat_regimes?.find((r) => r.value === p.effective_vat_regime)?.label}
                          {p.effective_vat_regime !== "fr" && " — autoliquidation"}</Text>
                      : <Select size="xs" w={260} aria-label="Régime TVA de la facture" allowDeselect={false}
                          data={data.meta.vat_regimes ?? []} value={p.effective_vat_regime} disabled={setRegime.isPending}
                          description={p.effective_vat_regime !== "fr" ? "Autoliquidation : TVA due et déductible du même montant." : undefined}
                          onChange={(v) => v && v !== p.effective_vat_regime && setRegime.mutate(v)} />}
                  </Row>
                )}
                {(p.supplier_vat || p.supplier_siret || p.supplier_iban) && (
                  <Row label={`Fournisseur (${fromQonto ? "Qonto" : "facture"})`}>
                    <Text size="sm" className="lv-num">{[p.supplier_vat, p.supplier_siret, p.supplier_iban].filter(Boolean).join(" ")}</Text></Row>
                )}
                {qonto && p.source === "manual" && (p.qonto_upload_status || (data.meta.qonto.upload && data.can_send)) && (
                  <Row label="Qonto">
                    <Group gap="sm">
                      {p.qonto_upload_status === "sent" ? <StatusBadge tone="ok">Déposée dans Qonto</StatusBadge>
                        : p.qonto_upload_status === "failed" ? <><StatusBadge tone="gap">Envoi en échec</StatusBadge><Text size="sm" c="var(--lv-brique)">{p.qonto_upload_error}</Text></>
                        : <Text size="sm" c="dimmed">Non envoyée</Text>}
                      <Can>{data.meta.qonto.upload && data.can_send && (
                        <ConfirmButton danger={false} size="compact-sm" variant="default" loading={sendToQonto.isPending}
                          title={p.qonto_upload_status === "failed" ? "Renvoyer la pièce à Qonto ?" : "Envoyer la pièce à Qonto ?"}
                          message="La pièce est déposée dans Qonto (factures fournisseurs)." confirmLabel="Envoyer"
                          onConfirm={() => sendToQonto.mutate()}>
                          {p.qonto_upload_status === "failed" ? "Renvoyer à Qonto" : "Envoyer à Qonto"}</ConfirmButton>
                      )}</Can>
                    </Group>
                  </Row>
                )}
                {p.attachment && (
                  <Row label="Pièce">
                    <Anchor href={p.attachment.url} target="_blank" rel="noopener" size="sm">{p.attachment.name}</Anchor>
                    <Text span size="sm" c="dimmed"> ({Math.round((p.attachment.size ?? 0) / 1024)} Ko)</Text>
                    {" · "}<Anchor href={`${p.attachment.url}?download=1`} size="sm">Télécharger</Anchor>
                    {" · "}<Anchor component="button" size="sm" onClick={() => setShowPreview((s) => !s)}>{showPreview ? "Masquer l'aperçu" : "Aperçu de la pièce"}</Anchor>
                  </Row>
                )}
              </Table.Tbody>
            </Table>
          </Paper>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 4 }}>
          {p.entry ? (
            <Paper p="md">
              <Text size="sm">Écriture <Anchor component={AppLink} href={p.entry.url} size="sm">{p.entry.reference}</Anchor> du {formatDate(p.entry.date)}</Text>
              <Can><ConfirmButton mt="sm" size="compact-md" title="Annuler la comptabilisation ?" message="L'écriture d'achat est supprimée ; la facture redevient modifiable."
                confirmLabel="Annuler la comptabilisation" loading={unpost.isPending} onConfirm={() => unpost.mutate()}>Annuler la comptabilisation</ConfirmButton></Can>
            </Paper>
          ) : p.state.code === "ready" && <Can><Button loading={post.isPending} onClick={() => post.mutate()}>Comptabiliser</Button></Can>}
        </Grid.Col>
      </Grid>

      {p.attachment && <Collapse expanded={showPreview} mb="md"><AttachmentPreview url={p.attachment.url} mime={p.attachment.mime} /></Collapse>}

      {data.awaiting_payment && (
        <Stack gap={4} mb="lg">
          <Group justify="space-between">
            <Title order={3}>Règlement</Title>
            {data.associate_payment && !data.associate_payment.blocker && (
              <Can><Button size="compact-sm" variant="default" onClick={() => setPayingByAssociate(true)}>Réglée par un associé</Button></Can>
            )}
          </Group>
          {data.paid_cents > 0 && (
            <Text size="sm">Déjà réglé : <MoneyText cents={data.paid_cents} size="sm" /> — restant à régler : <MoneyText cents={data.remaining_cents} size="sm" fw={600} /></Text>
          )}
          {data.suggestions.length ? (
            <>
              <Text size="sm" c="dimmed">Transactions bancaires libres autour de la date de la facture, d'un montant au plus égal au
                restant : cochez-en une ou plusieurs (règlement en plusieurs fois).</Text>
              <TransactionPicker remainingCents={data.remaining_cents} selected={picked} onChange={setPicked} disabled={!can.write}
                rows={data.suggestions.map((t) => ({ id: t.id, date: t.date, label: t.label, account: t.bank_account, amount_cents: t.amount_cents,
                  badges: <>
                    {t.exact && <Badge size="xs" color="lichen">montant exact</Badge>}
                    {t.rule && <Badge size="xs" color="paille" variant="light" title="Déjà passée par une règle : son écriture sera à remplacer">règle</Badge>}
                  </> }))} />
              <Can><Group justify="flex-end">
                <Button size="compact-md" loading={link.isPending}
                  disabled={!picked.length || selectedTotal(data.suggestions.map((t) => ({ ...t, account: t.bank_account })), picked) > data.remaining_cents}
                  onClick={() => link.mutate(picked, { onSuccess: () => setPicked([]) })}>
                  {picked.length > 1 ? `Régler avec ces ${picked.length} transactions` : "Régler avec cette transaction"}
                </Button>
              </Group></Can>
            </>
          ) : data.match_window && (
            <Text size="sm" c="dimmed">{data.paid_cents > 0 ? "Partiellement réglée" : "Non réglée"} : aucune transaction bancaire libre d'au plus <MoneyText cents={data.remaining_cents} size="sm" /> entre
              le {formatDate(data.match_window[0])} et le {formatDate(data.match_window[1])}. Le règlement sera passé automatiquement à la
              synchronisation Qonto ou à l'import du relevé (OFX) qui la contient ; une ligne plus tardive se rattache depuis
              Banque › Transactions (« Rattacher à une facture »).</Text>
          )}
        </Stack>
      )}

      {data.payments.length > 0 && (
        <Stack gap={4} mb="lg">
          <Title order={3}>Règlements</Title>
          <Table>
            <Table.Thead><Table.Tr><Table.Th>Date</Table.Th><Table.Th>Compte bancaire</Table.Th><Table.Th>Libellé</Table.Th><Table.Th ta="right">Montant</Table.Th><Table.Th>État</Table.Th><Table.Th /></Table.Tr></Table.Thead>
            <Table.Tbody>{data.payments.map((pay) => (
              <Table.Tr key={pay.id}>
                {pay.origin === "associate" ? <>
                  <Table.Td className="lv-num">{formatDate(pay.date ?? null)}</Table.Td>
                  <Table.Td><Anchor component={AppLink} href={`/associates/${pay.associate?.id}`} size="sm">Compte courant — {pay.associate?.name}</Anchor></Table.Td>
                  <Table.Td><Text size="sm">Réglée par l'associé</Text></Table.Td>
                  <Table.Td ta="right"><MoneyText cents={-(pay.amount_cents ?? 0)} /></Table.Td>
                </> : pay.transaction ? <>
                  <Table.Td className="lv-num">{formatDate(pay.transaction.date)}</Table.Td>
                  <Table.Td><Anchor component={AppLink} href={`/bank-accounts/${pay.transaction.bank_account_id}/transactions`} size="sm">{pay.transaction.bank_account}</Anchor></Table.Td>
                  <Table.Td><Text size="sm">{pay.transaction.label}</Text></Table.Td>
                  <Table.Td ta="right"><MoneyText cents={pay.transaction.amount_cents} /></Table.Td>
                </> : <Table.Td colSpan={4}><Text size="sm" c="dimmed">Transaction Qonto pas encore importée ({pay.qonto_transaction_id}) — synchronisez le compte bancaire.</Text></Table.Td>}
                <Table.Td>
                  <Group gap={6}>
                    {pay.status === "other_entry"
                      ? <Anchor component={AppLink} href="/purchases/settlements"><StatusBadge tone="gap">{pay.status_label}</StatusBadge></Anchor>
                      : <StatusBadge tone={PAYMENT_TONES[pay.status]}>{pay.status_label}</StatusBadge>}
                    {pay.entry && <Anchor component={AppLink} href={pay.entry.url} size="sm">{pay.entry.reference}</Anchor>}
                  </Group>
                </Table.Td>
                <Table.Td ta="right">{pay.origin !== "qonto" && (
                  <Group gap={6} justify="flex-end" wrap="nowrap">
                    <Text size="xs" c="dimmed">{pay.origin === "match" ? "auto" : pay.origin === "associate" ? "associé" : "choisi"}</Text>
                    <Can><ConfirmButton size="compact-sm" variant="subtle" title="Défaire ce règlement ?" message="Son écriture sera supprimée."
                      confirmLabel="Défaire" onConfirm={() => unlink.mutate(pay.id)}>Défaire</ConfirmButton></Can>
                  </Group>
                )}</Table.Td>
              </Table.Tr>
            ))}</Table.Tbody>
          </Table>
        </Stack>
      )}

      <Title order={3} mb={4}>Lignes</Title>
      {editable && can.write ? (
        <form onSubmit={(e) => { e.preventDefault(); saveLines.mutate(rows); }}>
          <LinesEditor rows={rows} onChange={setRows} products={data.meta.products} accounts={data.meta.charge_accounts} projects={data.meta.projects}
            expected={p.total_cents} expectedLabel={fromQonto ? "TTC Qonto" : "TTC"} />
          <Group mt="sm"><Button type="submit" loading={saveLines.isPending}>Enregistrer les lignes</Button></Group>
          <Text size="xs" c="dimmed" mt={4}>TVA laissée vide : calculée à partir du taux. Une remise obtenue se saisit en ligne négative (609).
            Les lignes enregistrées ne sont plus modifiées par la synchronisation ; la facture est comptabilisée dès que tout est complet.</Text>
        </form>
      ) : (
        <Table>
          <Table.Thead><Table.Tr><Table.Th>Produit</Table.Th><Table.Th>Compte</Table.Th><Table.Th>Libellé</Table.Th><Table.Th ta="right">HT</Table.Th>
            <Table.Th ta="right">Taux %</Table.Th><Table.Th ta="right">TVA</Table.Th><Table.Th ta="right">TTC</Table.Th><Table.Th /></Table.Tr></Table.Thead>
          <Table.Tbody>{data.lines_view.map((l, i) => (
            <Table.Tr key={i}>
              <Table.Td>{l.product ?? "—"}</Table.Td><Table.Td><Code>{l.account ?? "—"}</Code></Table.Td><Table.Td>{l.label}{l.project && <Text span size="xs" c="dimmed"> · projet {l.project}</Text>}</Table.Td>
              <Table.Td ta="right"><MoneyText cents={l.untaxed_cents} /></Table.Td><Table.Td ta="right" className="lv-num">{l.vat_rate ?? "?"}</Table.Td>
              <Table.Td ta="right"><MoneyText cents={l.vat_cents} /></Table.Td><Table.Td ta="right"><MoneyText cents={l.total_cents} /></Table.Td>
              <Table.Td>{l.asset_id ? <Anchor component={AppLink} href={`/assets/${l.asset_id}`} size="sm">Immobilisation</Anchor>
                : l.account?.startsWith("2") && p.journal_entry_id && can.write
                  ? <Button size="compact-xs" variant="subtle" loading={createAsset.isPending} onClick={() => createAsset.mutate(l.id!, {
                      onSuccess: (r) => goTo(`/assets/${r.item.id}`) })}>Créer l'immobilisation</Button> : null}</Table.Td>
            </Table.Tr>
          ))}</Table.Tbody>
          <Table.Tfoot><Table.Tr>
            <Table.Td colSpan={6} ta="right"><Text fw={600} size="sm">Total des lignes / TTC</Text></Table.Td>
            <Table.Td ta="right"><MoneyText cents={data.lines_view.reduce((s, l) => s + l.total_cents, 0)} fw={600} /> / <MoneyText cents={p.total_cents} /></Table.Td>
          </Table.Tr></Table.Tfoot>
        </Table>
      )}
      <FormModal opened={payingByAssociate && !!data.associate_payment} onClose={() => setPayingByAssociate(false)}
        title="Réglée par un associé">
        {data.associate_payment && <AssociatePaymentForm purchaseId={p.id} totalCents={p.total_cents}
          associates={data.associate_payment.associates} invalidate={[PURCHASES_KEY, ["associates"]]}
          onDone={() => setPayingByAssociate(false)} />}
      </FormModal>
    </>
  );
}
