// Banque › Prévisionnel : solde de trésorerie mois par mois sur 12 mois glissants (soldes actuels,
// factures non réglées, budget restant, saisies manuelles) ; alerte de solde négatif ; saisies
// manuelles avec répétition mensuelle.
import { useState } from "react";
import { Alert, Anchor, Button, Center, Group, Loader, Paper, SegmentedControl, Select, SimpleGrid, Table, Text, TextInput, Title } from "@mantine/core";
import { CompositeChart } from "@mantine/charts";
import { DateInput } from "@mantine/dates";
import { useForm } from "@mantine/form";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { applyApiError, FormBody } from "../../components/ApiForm";
import { Can } from "../../components/Can";
import { confirmAction } from "../../components/ConfirmButton";
import { FormModal } from "../../components/FormModal";
import { MoneyInput, MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { useCan } from "../../api/session";
import { formatDate, formatEuros } from "../../lib/format";
import { AppLink } from "../../app/navigation";

type Category = "customers" | "purchases" | "budget" | "manual";
interface Month {
  month: string; label: string; opening_cents: number; closing_cents: number; inflow_cents: number; outflow_cents: number;
  inflows: Record<Category, number>; outflows: Record<Category, number>;
  details: { category: Category; label: string; amount_cents: number; url: string | null }[];
}
interface Item { id: number; date: string; label: string; amount_cents: number; bank_account_id: number | null;
  bank_account: string | null; repeat_monthly_until: string | null }
export interface Forecast {
  today: string; opening_cents: number; months: Month[]; categories: Record<Category, string>;
  first_negative: { month: string; closing_cents: number } | null;
  accounts: { label: string; account: string; ledger_cents: number; unbooked_cents: number; balance_cents: number }[];
  items: Item[]; bank_accounts: { value: string; label: string }[];
}

export const FORECAST_KEY = ["cash-forecast"];
const ORDER: Category[] = ["customers", "purchases", "budget", "manual"];
// Colonne des libellés figée pendant le défilement horizontal des mois.
const STICKY = { position: "sticky", left: 0, zIndex: 3, background: "var(--lv-surface)", whiteSpace: "nowrap" } as const;

export function useForecast() {
  return useQuery({ queryKey: FORECAST_KEY, queryFn: () => api.get<Forecast>("/api/v1/cash-forecast") });
}

export function NegativeAlert({ forecast }: { forecast: Forecast }) {
  if (!forecast.first_negative) return null;
  const month = forecast.months.find((m) => m.month === forecast.first_negative?.month);
  return (
    <Alert color="brique" title="Trésorerie négative prévue">
      Solde prévu de <MoneyText cents={forecast.first_negative.closing_cents} anomaly /> fin {month?.label ?? ""} ·{" "}
      <Anchor component={AppLink} href="/treasury/forecast" size="sm">voir le prévisionnel</Anchor>
    </Alert>
  );
}

function ItemForm({ item, banks, onDone }: { item: Item | null; banks: Forecast["bank_accounts"]; onDone: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const form = useForm({ initialValues: {
    label: item?.label ?? "", date: item?.date ?? (null as string | null), direction: (item && item.amount_cents > 0) ? "in" : "out",
    amount: item ? Math.abs(item.amount_cents) : (null as number | null), repeat_monthly_until: item?.repeat_monthly_until ?? (null as string | null),
    bank_account_id: item?.bank_account_id ? String(item.bank_account_id) : (null as string | null),
  } });
  const save = useAction((v: typeof form.values) => {
    const body = { label: v.label, date: v.date, repeat_monthly_until: v.repeat_monthly_until, bank_account_id: v.bank_account_id,
      amount_cents: v.amount === null ? 0 : (v.direction === "in" ? v.amount : -v.amount) };
    return item ? api.put<{ notices: Notice[] }>(`/api/v1/cash-forecast/items/${item.id}`, body)
      : api.post<{ notices: Notice[] }>("/api/v1/cash-forecast/items", body);
  }, { invalidate: [FORECAST_KEY], silent: true });
  return (
    <form onSubmit={form.onSubmit((v) => save.mutate(v, { onSuccess: onDone, onError: (e) => setError(applyApiError(form, e)) }))}>
      <FormBody error={error} submitLabel={item ? "Enregistrer" : "Ajouter"} onCancel={onDone} loading={save.isPending}>
        <TextInput label="Libellé" required data-autofocus placeholder="Loyer, subvention attendue…" {...form.getInputProps("label")} />
        <SegmentedControl data={[{ value: "out", label: "Décaissement" }, { value: "in", label: "Encaissement" }]} {...form.getInputProps("direction")} />
        <Group grow>
          <DateInput label="Date" required valueFormat="DD/MM/YYYY" {...form.getInputProps("date")} />
          <MoneyInput label="Montant" required value={form.values.amount} onChange={(v) => form.setFieldValue("amount", v)}
            error={form.errors.amount_cents} />
        </Group>
        <DateInput label="Répéter chaque mois jusqu'au" clearable valueFormat="DD/MM/YYYY" {...form.getInputProps("repeat_monthly_until")} />
        {banks.length > 1 && <Select label="Compte bancaire" clearable data={banks} {...form.getInputProps("bank_account_id")} />}
      </FormBody>
    </form>
  );
}

export default function CashForecastPage() {
  const can = useCan();
  const { data } = useForecast();
  const [editing, setEditing] = useState<Item | "new" | null>(null);
  const [opened, setOpened] = useState<string | null>(null);
  const remove = useAction((id: number) => api.delete<{ notices: Notice[] }>(`/api/v1/cash-forecast/items/${id}`), { invalidate: [FORECAST_KEY] });
  if (!data) return <Center h={300}><Loader /></Center>;
  const chart = data.months.map((m) => ({ mois: m.label, Encaissements: m.inflow_cents / 100, Décaissements: m.outflow_cents / 100,
    Solde: m.closing_cents / 100 }));
  const detail = data.months.find((m) => m.month === opened);
  return (
    <>
      <PageHeader title="Prévisionnel de trésorerie" description={`12 mois à partir de ${data.months[0]?.label} · soldes au ${formatDate(data.today)}`}
        actions={<Can><Button onClick={() => setEditing("new")}>Ajouter une saisie</Button></Can>} />
      <NegativeAlert forecast={data} />
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} my="md">
        <Paper p="md"><Text size="sm" c="dimmed">Trésorerie actuelle</Text>
          <Text fz={24} fw={500} className="lv-num"><MoneyText cents={data.opening_cents} anomaly={data.opening_cents < 0} /></Text></Paper>
        {data.accounts.map((a) => (
          <Paper p="md" key={a.account}><Text size="sm" c="dimmed">{a.label} <span className="lv-num">({a.account})</span></Text>
            <Text fw={500} className="lv-num"><MoneyText cents={a.balance_cents} /></Text>
            {a.unbooked_cents !== 0 && <Text size="xs" c="dimmed">dont <MoneyText cents={a.unbooked_cents} size="xs" /> de transactions non comptabilisées</Text>}
          </Paper>
        ))}
      </SimpleGrid>
      <Paper p="md" mb="md">
        <CompositeChart h={280} data={chart} dataKey="mois" withLegend valueFormatter={(v) => formatEuros(Math.round(v * 100))}
          referenceLines={[{ y: 0, color: "var(--lv-brique)" }]}
          series={[{ name: "Encaissements", color: "var(--lv-lichen)", type: "bar" }, { name: "Décaissements", color: "var(--lv-ardoise)", type: "bar" },
            { name: "Solde", color: "var(--lv-paille-ink)", type: "line" }]} />
      </Paper>
      <Paper p={0} mb="md" style={{ overflowX: "auto" }}>
        <Table verticalSpacing={4} miw={1400}>
          <Table.Thead bg="var(--lv-sauge)"><Table.Tr><Table.Th miw={190} style={{ ...STICKY, background: "var(--lv-sauge)" }} />
            {data.months.map((m) => <Table.Th key={m.month} ta="right">
              <Anchor component="button" size="sm" fw={700} onClick={() => setOpened(m.month)}>{m.label}</Anchor></Table.Th>)}
          </Table.Tr></Table.Thead>
          <Table.Tbody>
            <Table.Tr><Table.Td style={STICKY}><Text size="sm" fw={600}>Solde début</Text></Table.Td>
              {data.months.map((m) => <Table.Td key={m.month} ta="right"><MoneyText cents={m.opening_cents} size="sm" /></Table.Td>)}</Table.Tr>
            {ORDER.map((c) => (
              <Table.Tr key={`in-${c}`}><Table.Td style={STICKY}><Text size="sm">+ {data.categories[c]}</Text></Table.Td>
                {data.months.map((m) => <Table.Td key={m.month} ta="right">{m.inflows[c] ? <MoneyText cents={m.inflows[c]} size="sm" /> : <Text size="sm" c="dimmed">—</Text>}</Table.Td>)}</Table.Tr>
            ))}
            {ORDER.map((c) => (
              <Table.Tr key={`out-${c}`}><Table.Td style={STICKY}><Text size="sm">− {data.categories[c]}</Text></Table.Td>
                {data.months.map((m) => <Table.Td key={m.month} ta="right">{m.outflows[c] ? <MoneyText cents={-m.outflows[c]} size="sm" /> : <Text size="sm" c="dimmed">—</Text>}</Table.Td>)}</Table.Tr>
            ))}
            <Table.Tr><Table.Td style={STICKY}><Text size="sm" fw={700}>Solde fin</Text></Table.Td>
              {data.months.map((m) => <Table.Td key={m.month} ta="right"><MoneyText cents={m.closing_cents} size="sm" fw={700} anomaly={m.closing_cents < 0} /></Table.Td>)}</Table.Tr>
          </Table.Tbody>
        </Table>
      </Paper>
      <Title order={2} size="h4" mb="xs">Saisies manuelles</Title>
      <Paper p={0}>
        <Table verticalSpacing={4}>
          <Table.Tbody>
            {data.items.map((i) => (
              <Table.Tr key={i.id}>
                <Table.Td className="lv-num" w={110}>{formatDate(i.date)}</Table.Td>
                <Table.Td>{i.label}{i.repeat_monthly_until && <Text span size="xs" c="dimmed"> · chaque mois jusqu'au {formatDate(i.repeat_monthly_until)}</Text>}</Table.Td>
                <Table.Td ta="right"><MoneyText cents={i.amount_cents} plus /></Table.Td>
                {can.write && <Table.Td ta="right" w={200}>
                  <Button variant="subtle" size="compact-sm" onClick={() => setEditing(i)}>Modifier</Button>
                  <Button variant="subtle" size="compact-sm" color="brique" onClick={() => confirmAction({
                    title: `Retirer « ${i.label} » ?`, confirmLabel: "Retirer", onConfirm: () => remove.mutate(i.id) })}>Retirer</Button>
                </Table.Td>}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
        {data.items.length === 0 && <Text size="sm" c="dimmed" p="md">Aucune saisie : ajoutez un loyer, une subvention attendue, un salaire…</Text>}
      </Paper>
      <FormModal opened={editing !== null} onClose={() => setEditing(null)} title={editing === "new" ? "Ajouter une saisie" : "Modifier la saisie"}>
        {editing !== null && <ItemForm key={editing === "new" ? "new" : editing.id} item={editing === "new" ? null : editing}
          banks={data.bank_accounts} onDone={() => setEditing(null)} />}
      </FormModal>
      <FormModal opened={!!detail} onClose={() => setOpened(null)} title={`Mouvements prévus — ${detail?.label ?? ""}`} size="lg">
        {detail && (
          <Table verticalSpacing={4}>
            <Table.Tbody>
              {detail.details.map((d, i) => (
                <Table.Tr key={i}>
                  <Table.Td><Text size="xs" c="dimmed">{data.categories[d.category]}</Text></Table.Td>
                  <Table.Td>{d.url ? <Anchor component={AppLink} href={d.url} size="sm">{d.label}</Anchor> : <Text size="sm">{d.label}</Text>}</Table.Td>
                  <Table.Td ta="right"><MoneyText cents={d.amount_cents} plus size="sm" /></Table.Td>
                </Table.Tr>
              ))}
              {detail.details.length === 0 && <Table.Tr><Table.Td><Text size="sm" c="dimmed">Aucun mouvement prévu.</Text></Table.Td></Table.Tr>}
            </Table.Tbody>
          </Table>
        )}
      </FormModal>
    </>
  );
}
