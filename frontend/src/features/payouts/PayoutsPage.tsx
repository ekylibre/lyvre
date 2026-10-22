// Banque › Versements Stancer : liste par mois, synchronisation en arrière-plan.
import { useState } from "react";
import { Anchor, Button, Text } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, useList, type Notice } from "../../api/resources";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { IntegrationNotice } from "../../components/IntegrationNotice";
import { JobStatus, type Job } from "../../components/JobStatus";
import { MoneyText } from "../../components/Money";
import { MonthSelect, type MonthOption } from "../../components/MonthSelect";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge, type Tone } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink } from "../../app/navigation";

export interface Payout {
  id: number; stancer_id: string; date_payout: string | null; date_bank: string | null; description: string;
  amount_cents: number; fees_cents: number; currency: string; status: string; status_label: string; payments: number;
  imported_at: string | null; bank_transaction: { date: string; amount_cents: number; label: string } | null;
}
export interface StancerMeta { months: MonthOption[]; stancer: { available: boolean; message: string | null }; job: Job | null }

export const PAYOUTS_KEY = ["payouts"];
export const PAYOUT_TONES: Record<string, Tone> = { paid: "ok", done: "ok", failed: "gap", in_progress: "info", to_pay: "todo", pending: "todo" };

export function syncResult(r: Record<string, unknown>) {
  return (
    <Text size="sm">
      {r.imported !== undefined && `${r.imported} versement(s) importé(s), ${r.updated} mis à jour sur ${r.total}. `}
      {r.payments_total !== undefined && `Paiements : ${r.payments_imported} importé(s), ${r.payments_updated} mis à jour sur ${r.payments_total}.`}
    </Text>
  );
}

const COLUMNS: GridColumn<Payout>[] = [
  { accessor: "date_payout", title: "Date du versement", sortable: true, hideable: false, render: (p) => <span className="lv-num">{formatDate(p.date_payout)}</span> },
  { accessor: "date_bank", title: "Date banque", render: (p) => <span className="lv-num">{formatDate(p.date_bank)}</span> },
  { accessor: "stancer_id", title: "Identifiant Stancer", render: (p) => <Anchor component={AppLink} href={`/payouts/${p.id}`} className="lv-num" size="sm">{p.stancer_id}</Anchor> },
  { accessor: "description", title: "Description" },
  { accessor: "amount_cents", title: "Montant", textAlign: "right", render: (p) => <MoneyText cents={p.amount_cents} /> },
  { accessor: "fees_cents", title: "Frais", textAlign: "right", render: (p) => <MoneyText cents={p.fees_cents} c="dimmed" /> },
  { accessor: "payments", title: "Paiements", textAlign: "right", render: (p) => <span className="lv-num">{p.payments}</span> },
  { accessor: "bank_transaction", title: "Banque", render: (p) => p.bank_transaction ? <StatusBadge tone="ok">Reçu</StatusBadge> : <Text c="dimmed">—</Text> },
  { accessor: "status", title: "Statut", render: (p) => <StatusBadge tone={PAYOUT_TONES[p.status] ?? "neutral"}>{p.status_label}</StatusBadge> },
];

export default function PayoutsPage() {
  const client = useQueryClient();
  const [params, setParams] = useUrlParams({ month: "", sort: "desc" });
  const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
  const { data, isFetching } = useList<Payout, StancerMeta>(PAYOUTS_KEY, `/api/v1/payouts${query ? `?${query}` : ""}`);
  const [job, setJob] = useState<Job | null>(null);
  const shown = job ?? data?.meta?.job ?? null;
  const start = useAction<void, { job: Job; notices?: Notice[] }>(() => api.post("/api/v1/payouts/sync"));
  return (
    <>
      <PageHeader title="Versements Stancer" description="Versements reçus de Stancer et paiements qu'ils regroupent."
        actions={<Button loading={start.isPending} disabled={!data?.meta?.stancer.available || shown?.status === "running"}
          onClick={() => start.mutate(undefined, { onSuccess: (r) => setJob(r.job) })}>Synchroniser Stancer</Button>} />
      <IntegrationNotice name="stancer" state={data?.meta?.stancer} consequence="synchronisation impossible" />
      {shown && <JobStatus key={shown.id} job={shown} renderResult={syncResult}
        onDone={() => void client.invalidateQueries({ queryKey: PAYOUTS_KEY })} />}
      <FilterBar><MonthSelect value={params.month} onChange={(month) => setParams({ month })} options={data?.meta?.months} /></FilterBar>
      <DataGrid id="payouts" records={data?.items} columns={COLUMNS} fetching={isFetching}
        sort={{ column: "date_payout", direction: params.sort === "asc" ? "asc" : "desc" }} onSortChange={(s) => setParams({ sort: s.direction })}
        emptyText="Aucun versement : lancez une synchronisation." />
    </>
  );
}
