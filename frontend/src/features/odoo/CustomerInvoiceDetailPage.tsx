// Ventes › Facture client : montants, informations, lignes, note.
import { useParams } from "react-router";
import { Alert, Button, Center, Grid, Loader, Paper, SimpleGrid, Table, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { isDue, Partner, type CustomerInvoice } from "./CustomerInvoicesPage";
import { Amount } from "./OrderDetailPage";
import { INVOICES_KEY, INVOICE_TONES, PAYMENT_TONES, quantity } from "./types";

interface Detail {
  item: CustomerInvoice & { origin: string | null; currency: string; journal: string | null; partner_email: string | null; narration: string | null };
  lines: { id: number; product: string | null; description: string; qty: number; unit_cents: number; discount: number; subtotal_cents: number; total_cents: number }[];
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return <Table.Tr><Table.Th w="40%" fw={500} c="dimmed">{label}</Table.Th><Table.Td>{children}</Table.Td></Table.Tr>;
}

export default function CustomerInvoiceDetailPage() {
  const id = Number(useParams().invoice_id);
  const { data, error } = useQuery({ queryKey: [...INVOICES_KEY, id], retry: false,
    queryFn: () => api.get<Detail>(`/api/v1/customer-invoices/${id}`) });
  if (error) return <Alert color="brique" mt="md">{(error as Error).message}</Alert>;
  if (!data) return <Center h={300}><Loader /></Center>;
  const inv = data.item;
  return (
    <>
      <PageHeader title={inv.number}
        description={[inv.date && `Émise le ${formatDate(inv.date)}`, inv.due_date && `échéance ${formatDate(inv.due_date)}`, inv.journal]
          .filter(Boolean).join(" · ")}
        actions={<Button variant="default" component={AppLink} href="/customer-invoices/">Retour</Button>} />
      <SimpleGrid cols={{ base: 2, md: 4 }} mb="md">
        <Amount label="Total HT" cents={inv.untaxed_cents} /><Amount label="TVA" cents={inv.tax_cents} />
        <Amount label="Total TTC" cents={inv.total_cents} /><Amount label="Reste dû" cents={inv.residual_cents} anomaly={isDue(inv)} />
      </SimpleGrid>
      <Grid mb="lg">
        <Grid.Col span={{ base: 12, md: 6 }}><Paper p="xs"><Table><Table.Tbody>
          <Row label="Numéro"><span className="lv-num">{inv.number}</span></Row><Row label="Référence">{inv.ref ?? "—"}</Row>
          <Row label="Origine">{inv.origin ?? "—"}</Row><Row label="Devise">{inv.currency}</Row>
        </Table.Tbody></Table></Paper></Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}><Paper p="xs"><Table><Table.Tbody>
          <Row label="Client"><Partner inv={inv} /></Row><Row label="Email">{inv.partner_email ?? "—"}</Row>
          <Row label="État comptable"><StatusBadge tone={INVOICE_TONES[inv.state ?? ""] ?? "neutral"}>{inv.state_label}</StatusBadge></Row>
          <Row label="État paiement"><StatusBadge tone={PAYMENT_TONES[inv.payment_state ?? ""] ?? "neutral"}>{inv.payment_state_label}</StatusBadge></Row>
        </Table.Tbody></Table></Paper></Grid.Col>
      </Grid>
      <Title order={3} mb={4}>Lignes</Title>
      <Table>
        <Table.Thead><Table.Tr><Table.Th>Produit</Table.Th><Table.Th>Description</Table.Th><Table.Th ta="right">Qté</Table.Th><Table.Th ta="right">PU</Table.Th>
          <Table.Th ta="right">Remise %</Table.Th><Table.Th ta="right">Sous-total HT</Table.Th><Table.Th ta="right">Total TTC</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>
          {data.lines.map((l) => (
            <Table.Tr key={l.id}><Table.Td>{l.product ?? "—"}</Table.Td><Table.Td><Text size="sm" c="dimmed">{l.description}</Text></Table.Td>
              <Table.Td ta="right" className="lv-num">{quantity(l.qty)}</Table.Td><Table.Td ta="right"><MoneyText cents={l.unit_cents} /></Table.Td>
              <Table.Td ta="right" className="lv-num">{quantity(l.discount)}</Table.Td><Table.Td ta="right"><MoneyText cents={l.subtotal_cents} /></Table.Td>
              <Table.Td ta="right"><MoneyText cents={l.total_cents} /></Table.Td></Table.Tr>
          ))}
          {!data.lines.length && <Table.Tr><Table.Td colSpan={7}><Text c="dimmed" ta="center" size="sm">Aucune ligne produit.</Text></Table.Td></Table.Tr>}
        </Table.Tbody>
      </Table>
      {inv.narration && <><Title order={3} mt="lg" mb={4}>Note</Title><Paper p="md"><Text size="sm" c="dimmed" style={{ whiteSpace: "pre-line" }}>{inv.narration}</Text></Paper></>}
    </>
  );
}
