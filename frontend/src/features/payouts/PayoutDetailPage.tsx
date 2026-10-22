// Versement Stancer : informations, opération bancaire, paiements ; synchronisation des paiements.
import { useState } from "react";
import { useParams } from "react-router";
import { Button, Center, Loader, Paper, SimpleGrid, Text } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { JobStatus, type Job } from "../../components/JobStatus";
import { MoneyText } from "../../components/Money";
import { MonthSelect } from "../../components/MonthSelect";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";
import { PAYOUT_TONES, PAYOUTS_KEY, syncResult, type Payout, type StancerMeta } from "./PayoutsPage";

interface Payment { id: number; stancer_id: string; date: string | null; method: string | null; customer: string; description: string;
  amount_cents: number; status: string | null; status_label: string | null }

const COLUMNS: GridColumn<Payment>[] = [
  { accessor: "date", title: "Date", hideable: false, render: (p) => <span className="lv-num">{formatDate(p.date)}</span> },
  { accessor: "stancer_id", title: "Identifiant Stancer", render: (p) => <Text size="sm" className="lv-num">{p.stancer_id}</Text> },
  { accessor: "method", title: "Moyen" },
  { accessor: "customer", title: "Client" },
  { accessor: "description", title: "Description" },
  { accessor: "amount_cents", title: "Montant", textAlign: "right", render: (p) => <MoneyText cents={p.amount_cents} /> },
  { accessor: "status", title: "Statut", render: (p) => <StatusBadge tone={p.status === "paid" || p.status === "captured" ? "ok" : p.status === "refused" || p.status === "disputed" ? "gap" : "neutral"}>{p.status_label ?? "—"}</StatusBadge> },
];

function Info({ label, children }: { label: string; children: React.ReactNode }) {
  return <Paper p="md"><Text size="sm" c="dimmed">{label}</Text><Text>{children}</Text></Paper>;
}

export default function PayoutDetailPage() {
  const id = Number(useParams().payout_id);
  const client = useQueryClient();
  const [params, setParams] = useUrlParams({ month: "", sort: "desc" });
  const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
  const key = [...PAYOUTS_KEY, id, query];
  const { data } = useQuery({ queryKey: key, placeholderData: (prev) => prev,
    queryFn: () => api.get<{ item: Payout; payments: Payment[]; meta: StancerMeta }>(`/api/v1/payouts/${id}${query ? `?${query}` : ""}`) });
  const [job, setJob] = useState<Job | null>(null);
  const start = useAction<void, { job: Job; notices?: Notice[] }>(() => api.post(`/api/v1/payouts/${id}/sync-payments`));
  if (!data) return <Center h={300}><Loader /></Center>;
  const p = data.item;
  const shown = job ?? data.meta.job;
  const total = data.payments.reduce((s, x) => s + x.amount_cents, 0);
  return (
    <>
      <PageHeader title={`Versement du ${formatDate(p.date_payout)}`} description={p.stancer_id}
        actions={<>
          <Button variant="default" component={AppLink} href="/payouts/">Retour aux versements</Button>
          <Button loading={start.isPending} disabled={!data.meta.stancer.available || shown?.status === "running"}
            onClick={() => start.mutate(undefined, { onSuccess: (r) => setJob(r.job) })}>Synchroniser les paiements</Button>
        </>} />
      {shown && <JobStatus key={shown.id} job={shown} renderResult={syncResult}
        onDone={() => void client.invalidateQueries({ queryKey: [...PAYOUTS_KEY, id] })} />}
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} mb="md">
        <Info label="Montant"><MoneyText cents={p.amount_cents} fw={600} /> <Text span size="sm" c="dimmed">frais <MoneyText cents={p.fees_cents} /></Text></Info>
        <Info label="Statut"><StatusBadge tone={PAYOUT_TONES[p.status] ?? "neutral"}>{p.status_label}</StatusBadge></Info>
        <Info label="Date banque"><span className="lv-num">{formatDate(p.date_bank)}</span></Info>
        <Info label="Opération bancaire">{p.bank_transaction
          ? <><span className="lv-num">{formatDate(p.bank_transaction.date)}</span> · <MoneyText cents={p.bank_transaction.amount_cents} /></>
          : "Non reçue"}</Info>
      </SimpleGrid>
      {p.description && <Text mb="sm">{p.description}</Text>}
      <FilterBar><MonthSelect value={params.month} onChange={(month) => setParams({ month })} options={data.meta.months} /></FilterBar>
      <DataGrid id="payout-payments" records={data.payments} columns={COLUMNS}
        sort={{ column: "date", direction: params.sort === "asc" ? "asc" : "desc" }} onSortChange={(s) => setParams({ sort: s.direction })}
        toolbar={<Text size="sm">{data.payments.length} paiement(s) · total <MoneyText cents={total} fw={600} /></Text>}
        emptyText="Aucun paiement : synchronisez les paiements du versement." />
    </>
  );
}
