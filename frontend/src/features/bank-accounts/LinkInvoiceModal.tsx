// « Rattacher à une facture » : une ligne de relevé règle (débit : facture d'achat saisie) ou encaisse
// (crédit : facture de vente) une facture existante, en tout ou partie. Une même facture reçoit ainsi
// plusieurs lignes, une à une ; l'écriture de règlement est passée et rapprochée de la ligne.
import { useState } from "react";
import { Alert, Anchor, Badge, Button, Center, Group, Loader, Radio, Stack, Table, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { FormModal } from "../../components/FormModal";
import { MoneyText } from "../../components/Money";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { PURCHASES_KEY } from "../purchases/types";
import { SALES_KEY } from "../sales/types";
import { BANK_ACCOUNTS_KEY } from "./types";

export type LinkableTransaction = { id: number; date: string; label: string; amount_cents: number };

type OpenInvoice = {
  id: number; number: string; entity: string | null; date: string | null; total_cents: number;
  remaining_cents: number; credit_note: boolean; same_entity: boolean; url: string;
};
type OpenInvoices = { kind: "purchase" | "sale"; amount_cents: number; items: OpenInvoice[] };

export function LinkInvoiceModal({ txn, onClose }: { txn: LinkableTransaction | null; onClose: () => void }) {
  const [chosen, setChosen] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: [...BANK_ACCOUNTS_KEY, "open-invoices", txn?.id], enabled: txn !== null, retry: false,
    queryFn: () => api.get<OpenInvoices>(`/api/v1/bank-transactions/${txn!.id}/open-invoices`),
  });
  const link = useAction((invoice: OpenInvoice) => (data!.kind === "purchase"
    ? api.post<{ notices: Notice[] }>(`/api/v1/purchases/${invoice.id}/payments`, { bank_transaction_ids: [txn!.id] })
    : api.post<{ notices: Notice[] }>(`/api/v1/sales/${invoice.id}/match`, { bank_transaction_ids: [txn!.id] })),
  { invalidate: [BANK_ACCOUNTS_KEY, PURCHASES_KEY, SALES_KEY] });
  const close = () => { setChosen(""); onClose(); };
  const invoice = data?.items.find((i) => String(i.id) === chosen);
  const what = data?.kind === "sale" ? "encaisser" : "régler";

  return (
    <FormModal opened={txn !== null} onClose={close} title="Rattacher à une facture" size="lg">
      {txn && <Stack>
        <Text size="sm">{formatDate(txn.date)} — {txn.label || "(sans libellé)"} — <MoneyText cents={txn.amount_cents} /></Text>
        {isLoading || !data ? <Center h={80}><Loader size="sm" /></Center> : data.items.length === 0 ? (
          <Alert color="ardoise">
            Aucune facture {data.kind === "sale" ? "de vente" : "d'achat comptabilisée"} n'attend un {data.kind === "sale" ? "encaissement" : "règlement"} d'au
            moins <MoneyText cents={Math.abs(txn.amount_cents)} size="sm" />. Créez la facture, ou passez une écriture.
          </Alert>
        ) : (
          <>
            <Text size="sm" c="dimmed">
              Factures {data.kind === "sale" ? "de vente" : "d'achat"} dont le restant est au moins égal au montant de la ligne. La ligne
              vient en déduction du restant : une facture se {what} en une ou plusieurs lignes.
            </Text>
            <Radio.Group value={chosen} onChange={setChosen}>
              <Table>
                <Table.Thead><Table.Tr>
                  <Table.Th w={30} /><Table.Th>Facture</Table.Th><Table.Th>Tiers</Table.Th>
                  <Table.Th ta="right">Total</Table.Th><Table.Th ta="right">Restant</Table.Th><Table.Th />
                </Table.Tr></Table.Thead>
                <Table.Tbody>{data.items.map((i) => (
                  <Table.Tr key={i.id}>
                    <Table.Td><Radio value={String(i.id)} aria-label={`${i.credit_note ? "Avoir" : "Facture"} ${i.number}`} /></Table.Td>
                    <Table.Td>
                      <Anchor component={AppLink} href={i.url} size="sm">{i.credit_note ? "Avoir" : "Facture"} {i.number}</Anchor>
                      <Text size="xs" c="dimmed">{formatDate(i.date)}</Text>
                    </Table.Td>
                    <Table.Td><Text size="sm">{i.entity ?? "—"}</Text></Table.Td>
                    <Table.Td ta="right"><MoneyText cents={i.total_cents} size="sm" /></Table.Td>
                    <Table.Td ta="right"><MoneyText cents={i.remaining_cents} size="sm" fw={600} /></Table.Td>
                    <Table.Td><Group gap={4} wrap="nowrap">
                      {i.remaining_cents === Math.abs(txn.amount_cents) && <Badge size="xs" color="lichen">solde la facture</Badge>}
                      {i.same_entity && <Badge size="xs" variant="light">même tiers</Badge>}
                    </Group></Table.Td>
                  </Table.Tr>
                ))}</Table.Tbody>
              </Table>
            </Radio.Group>
            {invoice && (
              <Text size="sm">
                Après rattachement, restant à {what} :{" "}
                <MoneyText cents={invoice.remaining_cents - Math.abs(txn.amount_cents)} size="sm" fw={600} />
              </Text>
            )}
          </>
        )}
        <Group justify="flex-end">
          <Button variant="default" onClick={close}>Annuler</Button>
          <Button disabled={!invoice} loading={link.isPending}
            onClick={() => invoice && link.mutate(invoice, { onSuccess: close })}>Rattacher</Button>
        </Group>
      </Stack>}
    </FormModal>
  );
}
