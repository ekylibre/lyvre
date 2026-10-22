// Ventes › Commande POS : montants, lignes et paiements.
import { useParams } from "react-router";
import { Alert, Button, Center, Loader, Paper, SimpleGrid, Table, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDateTime } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { ORDERS_KEY, ORDER_TONES, quantity } from "./types";

interface Detail {
  item: { reference: string; date: string | null; session: string | null; partner: string | null; total_cents: number;
    tax_cents: number; paid_cents: number; return_cents: number; state: string | null; state_label: string };
  lines: { id: number; product: string; qty: number; unit_cents: number; discount: number; subtotal_cents: number; total_cents: number }[];
  payments: { id: number; date: string | null; method: string | null; reference: string; card: string; amount_cents: number }[];
}

export function Amount({ label, cents, anomaly }: { label: string; cents: number; anomaly?: boolean }) {
  return <Paper p="md"><Text size="sm" c="dimmed">{label}</Text><MoneyText cents={cents} fw={700} size="xl" anomaly={anomaly} /></Paper>;
}

export default function OrderDetailPage() {
  const id = Number(useParams().order_id);
  const { data, error } = useQuery({ queryKey: [...ORDERS_KEY, id], retry: false,
    queryFn: () => api.get<Detail>(`/api/v1/orders/${id}`) });
  if (error) return <Alert color="brique" mt="md">{(error as Error).message}</Alert>;
  if (!data) return <Center h={300}><Loader /></Center>;
  const o = data.item;
  return (
    <>
      <PageHeader title={o.reference} description={<>{formatDateTime(o.date)} · session {o.session ?? "—"}{o.partner && ` · ${o.partner}`}{" "}
        <StatusBadge tone={ORDER_TONES[o.state ?? ""] ?? "neutral"}>{o.state_label}</StatusBadge></>}
        actions={<Button variant="default" component={AppLink} href="/orders/">Retour</Button>} />
      <SimpleGrid cols={{ base: 2, md: 4 }} mb="lg">
        <Amount label="Total TTC" cents={o.total_cents} /><Amount label="TVA" cents={o.tax_cents} />
        <Amount label="Payé" cents={o.paid_cents} /><Amount label="Rendu monnaie" cents={o.return_cents} />
      </SimpleGrid>
      <Title order={3} mb={4}>Lignes</Title>
      <Table mb="lg">
        <Table.Thead><Table.Tr><Table.Th>Produit</Table.Th><Table.Th ta="right">Qté</Table.Th><Table.Th ta="right">PU</Table.Th>
          <Table.Th ta="right">Remise %</Table.Th><Table.Th ta="right">Sous-total HT</Table.Th><Table.Th ta="right">Sous-total TTC</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>
          {data.lines.map((l) => (
            <Table.Tr key={l.id}><Table.Td>{l.product}</Table.Td><Table.Td ta="right" className="lv-num">{quantity(l.qty)}</Table.Td>
              <Table.Td ta="right"><MoneyText cents={l.unit_cents} /></Table.Td><Table.Td ta="right" className="lv-num">{quantity(l.discount)}</Table.Td>
              <Table.Td ta="right"><MoneyText cents={l.subtotal_cents} /></Table.Td><Table.Td ta="right"><MoneyText cents={l.total_cents} /></Table.Td></Table.Tr>
          ))}
          {!data.lines.length && <Table.Tr><Table.Td colSpan={6}><Text c="dimmed" ta="center" size="sm">Aucune ligne.</Text></Table.Td></Table.Tr>}
        </Table.Tbody>
      </Table>
      <Title order={3} mb={4}>Paiements</Title>
      <Table>
        <Table.Thead><Table.Tr><Table.Th>Date</Table.Th><Table.Th>Mode</Table.Th><Table.Th>Référence</Table.Th><Table.Th>Carte</Table.Th><Table.Th ta="right">Montant</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>
          {data.payments.map((p) => (
            <Table.Tr key={p.id}><Table.Td className="lv-num">{formatDateTime(p.date)}</Table.Td><Table.Td>{p.method ?? "—"}</Table.Td>
              <Table.Td className="lv-num">{p.reference}</Table.Td><Table.Td>{p.card}</Table.Td><Table.Td ta="right"><MoneyText cents={p.amount_cents} /></Table.Td></Table.Tr>
          ))}
          {!data.payments.length && <Table.Tr><Table.Td colSpan={5}><Text c="dimmed" ta="center" size="sm">Aucun paiement.</Text></Table.Td></Table.Tr>}
        </Table.Tbody>
      </Table>
    </>
  );
}
