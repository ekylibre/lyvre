// Compta › Aides et subventions (lot AG3.a, claudedocs/design_aides_pac.md § 8.4) : dossiers d'aide par campagne
// (montants demandé, notifié, versé, reste à percevoir, compte), fiche en tiroir avec les versements, nouvelle
// campagne PAC proposée d'après le profil de l'exploitation.
import { useState } from "react";
import {
  Alert, Button, Center, Checkbox, Drawer, Group, Loader, Paper, Select, SimpleGrid, Stack, Table, Text, TextInput,
  Textarea, Title,
} from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { ConfirmButton } from "../../components/ConfirmButton";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { FormModal } from "../../components/FormModal";
import { MoneyInput, MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge, type Tone } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { InvestmentSection, type AidInvestment } from "./InvestmentSection";
import { CapCheckCard } from "./CapCheckCard";

export const AIDS_KEY = ["aids"];

type Option = { value: string; label: string };
type AccountRef = { id: number; code: string; label: string };
export interface AidPayment {
  id: number; paid_on: string; amount_cents: number; kind: string; kind_label: string; note: string | null;
  bank_transaction: { id: number; label: string; transaction_date: string; amount_cents: number } | null;
}
export interface Aid {
  id: number; scheme: string; scheme_label: string; label: string; campaign: number; payer: string | null;
  nature: "operating" | "investment" | "mixed"; nature_label: string; account: AccountRef; operating_account: AccountRef | null;
  investment_share_cents: number | null; trigger: string; trigger_label: string; trigger_on: string | null;
  trigger_provisional: boolean; decision_on: string | null; requested_cents: number | null; notified_cents: number | null;
  notified_on: string | null; acquired_cents: number; paid_cents: number; remaining_cents: number;
  payment_request_deadline: string | null; payment_requested_on: string | null; commitment_end_on: string | null;
  status: "requested" | "granted" | "closed" | "refused"; status_label: string; notes: string | null; warnings: string[];
  payments?: AidPayment[];
  investment?: AidInvestment;
}
export interface AidList {
  items: Aid[]; totals: { requested_cents: number; acquired_cents: number; paid_cents: number; remaining_cents: number };
  meta: { natures: Option[]; triggers: Option[]; statuses: Option[]; payment_kinds: Option[]; campaigns: number[] };
}
interface Scheme {
  key: string; label: string; nature: string; trigger: string; payer: string | null;
  accounts: { code: string; label: string; exists: boolean }[];
}
interface Proposal { scheme: string; label: string; account: string; checked: boolean; reason: string | null; exists: boolean }

const TONES: Record<Aid["status"], Tone> = { requested: "todo", granted: "info", closed: "ok", refused: "neutral" };
const opts = { invalidate: [AIDS_KEY] };
type Saved = { item: Aid; notices: Notice[] };

function errorOf(e: unknown) {
  return e instanceof ApiError ? e.message : "Enregistrement impossible.";
}

function NewAidForm({ campaign, onDone }: { campaign: number; onDone: () => void }) {
  const { data } = useQuery({ queryKey: [...AIDS_KEY, "schemes"], queryFn: () => api.get<{ items: Scheme[] }>("/api/v1/aids/schemes") });
  const [schemeKey, setSchemeKey] = useState<string | null>(null);
  const [account, setAccount] = useState<string | null>(null);
  const [year, setYear] = useState(String(campaign));
  const [requested, setRequested] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const create = useAction((body: object) => api.post<Saved>("/api/v1/aids", body), opts);
  const scheme = data?.items.find((s) => s.key === schemeKey);
  const submit = () => {
    setError(null);
    create.mutateAsync({ scheme: schemeKey, campaign: Number(year), account_code: account ?? undefined, requested_cents: requested })
      .then(onDone, (e) => setError(errorOf(e)));
  };
  return (
    <form onSubmit={(e) => { e.preventDefault(); submit(); }}>
      <Stack>
        <Select label="Dispositif" required searchable data={(data?.items ?? []).map((s) => ({ value: s.key, label: s.label }))}
          value={schemeKey} onChange={(v) => { setSchemeKey(v); setAccount(null); }} />
        <TextInput label="Campagne" required value={year} onChange={(e) => setYear(e.currentTarget.value)} />
        {scheme && (
          <Select label="Compte" description="Le sous-compte proposé est créé sous son parent s'il manque."
            data={scheme.accounts.map((a) => ({ value: a.code, label: `${a.code} — ${a.label}` }))}
            value={account ?? scheme.accounts[0]?.code ?? null} onChange={setAccount} allowDeselect={false} />)}
        <MoneyInput label="Montant demandé" value={requested} onChange={setRequested} />
        {error && <Alert color="brique">{error}</Alert>}
        <Group><Button type="submit" disabled={!schemeKey} loading={create.isPending}>Créer le dossier</Button></Group>
      </Stack>
    </form>
  );
}

function PacCampaignForm({ campaign, onDone }: { campaign: number; onDone: () => void }) {
  const { data } = useQuery({ queryKey: [...AIDS_KEY, "pac", campaign],
    queryFn: () => api.get<{ items: Proposal[] }>(`/api/v1/aids/pac-campaign?campaign=${campaign}`) });
  const [picked, setPicked] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const create = useAction((body: object) => api.post<{ notices: Notice[] }>("/api/v1/aids/pac-campaign", body), opts);
  if (!data) return <Center h={120}><Loader /></Center>;
  const value = picked ?? data.items.filter((p) => p.checked).map((p) => p.scheme);
  return (
    <form onSubmit={(e) => { e.preventDefault(); create.mutateAsync({ campaign, schemes: value }).then(onDone, (er) => setError(errorOf(er))); }}>
      <Stack>
        <Text size="sm">Dossiers proposés d'après le profil de l'exploitation (Structure › Activités et démarches).</Text>
        <Checkbox.Group value={value} onChange={setPicked}>
          <Stack gap="xs">
            {data.items.map((p) => (
              <Checkbox key={p.scheme} value={p.scheme} disabled={p.exists}
                label={`${p.label} (${p.account})`}
                description={p.exists ? "déjà créé pour cette campagne" : p.reason ?? undefined} />))}
          </Stack>
        </Checkbox.Group>
        {error && <Alert color="brique">{error}</Alert>}
        <Group><Button type="submit" disabled={value.length === 0} loading={create.isPending}>Créer les dossiers {campaign}</Button></Group>
      </Stack>
    </form>
  );
}

function PaymentForm({ aid, kinds }: { aid: Aid; kinds: Option[] }) {
  const [paidOn, setPaidOn] = useState<string | null>(null);
  const [amount, setAmount] = useState<number | null>(null);
  const [kind, setKind] = useState<string | null>("advance");
  const [error, setError] = useState<string | null>(null);
  const add = useAction((body: object) => api.post<Saved>(`/api/v1/aids/${aid.id}/payments`, body), opts);
  const submit = () => {
    setError(null);
    const cents = amount === null ? null : kind === "clawback" ? -Math.abs(amount) : amount;
    add.mutateAsync({ paid_on: paidOn, amount_cents: cents, kind })
      .then(() => { setPaidOn(null); setAmount(null); }, (e) => setError(errorOf(e)));
  };
  return (
    <form onSubmit={(e) => { e.preventDefault(); submit(); }}>
      <Group align="end" gap="xs">
        <DateInput label="Versé le" required valueFormat="DD/MM/YYYY" value={paidOn} onChange={setPaidOn} w={140} />
        <MoneyInput label="Montant" required value={amount} onChange={setAmount} w={140} />
        <Select label="Type" data={kinds} value={kind} onChange={setKind} allowDeselect={false} w={150} />
        <Button type="submit" variant="light" loading={add.isPending}>Ajouter</Button>
      </Group>
      {error && <Alert color="brique" mt="xs">{error}</Alert>}
    </form>
  );
}

type Draft = Partial<Record<"label" | "notes" | "account_code" | "operating_account_code" | "status", string | null>>
  & Partial<Record<"requested_cents" | "notified_cents" | "investment_share_cents", number | null>>
  & Partial<Record<"decision_on" | "notified_on" | "payment_request_deadline" | "payment_requested_on" | "commitment_end_on", string | null>>;

function AidDrawer({ aidId, meta, onClose }: { aidId: number | null; meta: AidList["meta"]; onClose: () => void }) {
  const can = useCan();
  const { data } = useQuery({ queryKey: [...AIDS_KEY, aidId], enabled: aidId !== null,
    queryFn: () => api.get<{ item: Aid }>(`/api/v1/aids/${aidId}`) });
  const [draft, setDraft] = useState<Draft>({});
  const [error, setError] = useState<string | null>(null);
  const save = useAction((body: Draft) => api.put<Saved>(`/api/v1/aids/${aidId}`, body), opts);
  const remove = useAction(() => api.delete<{ notices: Notice[] }>(`/api/v1/aids/${aidId}`), opts);
  const removePayment = useAction((id: number) => api.delete<Saved>(`/api/v1/aids/${aidId}/payments/${id}`), opts);
  const aid = data?.item;
  const close = () => { setDraft({}); setError(null); onClose(); };
  const val = <K extends keyof Draft>(key: K, fallback: Draft[K]) => (key in draft ? draft[key] : fallback);
  const set = (patch: Draft) => setDraft((d) => ({ ...d, ...patch }));
  const readOnly = !can.write;
  return (
    <Drawer opened={aidId !== null} onClose={close} position="right" size="lg"
      title={aid ? `${aid.label} — campagne ${aid.campaign}` : ""}>
      {!aid ? <Center h={200}><Loader /></Center> : (
        <Stack>
          {aid.warnings.map((w) => <Alert key={w} color="paille">{w}</Alert>)}
          <Text size="sm">{aid.scheme_label} · {aid.nature_label} · {aid.trigger_label}
            {aid.trigger_on && ` : ${formatDate(aid.trigger_on)}${aid.trigger_provisional ? " (date à confirmer)" : ""}`}
            {aid.payer && ` · versée par ${aid.payer}`}</Text>
          <form onSubmit={(e) => { e.preventDefault(); setError(null); save.mutateAsync(draft).then(() => setDraft({}), (er) => setError(errorOf(er))); }}>
            <Stack gap="sm">
              <TextInput label="Libellé" disabled={readOnly} value={val("label", aid.label) ?? ""} onChange={(e) => set({ label: e.currentTarget.value })} />
              <Group grow>
                <TextInput label={aid.nature === "mixed" ? "Compte d'investissement" : "Compte"} disabled={readOnly}
                  value={val("account_code", aid.account.code) ?? ""} onChange={(e) => set({ account_code: e.currentTarget.value })}
                  description={aid.account.label} />
                {aid.nature === "mixed" && (
                  <TextInput label="Compte d'exploitation" disabled={readOnly} description={aid.operating_account?.label}
                    value={val("operating_account_code", aid.operating_account?.code ?? "") ?? ""}
                    onChange={(e) => set({ operating_account_code: e.currentTarget.value })} />)}
              </Group>
              <Group grow>
                <MoneyInput label="Demandé" disabled={readOnly} value={val("requested_cents", aid.requested_cents) ?? null}
                  onChange={(v) => set({ requested_cents: v })} />
                <MoneyInput label="Notifié" disabled={readOnly} value={val("notified_cents", aid.notified_cents) ?? null}
                  onChange={(v) => set({ notified_cents: v })} />
                <DateInput label="Notifié le" clearable disabled={readOnly} valueFormat="DD/MM/YYYY"
                  value={val("notified_on", aid.notified_on) ?? null} onChange={(v) => set({ notified_on: v })} />
              </Group>
              {aid.nature === "mixed" && (
                <MoneyInput label="Part d'investissement" description="Le reste est la part d'exploitation." disabled={readOnly}
                  value={val("investment_share_cents", aid.investment_share_cents) ?? null} onChange={(v) => set({ investment_share_cents: v })} />)}
              <Group grow>
                {aid.trigger === "decision" && (
                  <DateInput label="Décision d'attribution" clearable disabled={readOnly} valueFormat="DD/MM/YYYY"
                    value={val("decision_on", aid.decision_on) ?? null} onChange={(v) => set({ decision_on: v })} />)}
                <Select label="Statut" disabled={readOnly} data={meta.statuses} allowDeselect={false}
                  value={val("status", aid.status) ?? aid.status} onChange={(v) => set({ status: v })} />
              </Group>
              <Group grow>
                <DateInput label="Date limite de la demande de paiement" clearable disabled={readOnly} valueFormat="DD/MM/YYYY"
                  value={val("payment_request_deadline", aid.payment_request_deadline) ?? null} onChange={(v) => set({ payment_request_deadline: v })} />
                <DateInput label="Demande de paiement faite le" clearable disabled={readOnly} valueFormat="DD/MM/YYYY"
                  value={val("payment_requested_on", aid.payment_requested_on) ?? null} onChange={(v) => set({ payment_requested_on: v })} />
              </Group>
              <DateInput label="Fin d'engagement" clearable disabled={readOnly} valueFormat="DD/MM/YYYY"
                value={val("commitment_end_on", aid.commitment_end_on) ?? null} onChange={(v) => set({ commitment_end_on: v })} />
              <Textarea label="Notes" disabled={readOnly} autosize minRows={2} value={val("notes", aid.notes) ?? ""}
                onChange={(e) => set({ notes: e.currentTarget.value })} />
              {error && <Alert color="brique">{error}</Alert>}
              {can.write && <Group><Button type="submit" disabled={Object.keys(draft).length === 0} loading={save.isPending}>Enregistrer</Button></Group>}
            </Stack>
          </form>

          {aid.investment && <InvestmentSection aidId={aid.id} investment={aid.investment}
            hasPayments={(aid.payments ?? []).length > 0} invalidate={[AIDS_KEY]} />}
          <Title order={5}>Versements</Title>
          <Text size="sm">Acquis <MoneyText cents={aid.acquired_cents} /> · versé <MoneyText cents={aid.paid_cents} /> · reste{" "}
            <MoneyText cents={aid.remaining_cents} /></Text>
          {(aid.payments ?? []).length > 0 && (
            <Table>
              <Table.Tbody>
                {(aid.payments ?? []).map((p) => (
                  <Table.Tr key={p.id}>
                    <Table.Td>{formatDate(p.paid_on)}</Table.Td>
                    <Table.Td>{p.kind_label}{p.bank_transaction && <Text size="xs" c="dimmed">{p.bank_transaction.label}</Text>}</Table.Td>
                    <Table.Td ta="right"><MoneyText cents={p.amount_cents} /></Table.Td>
                    <Table.Td>{can.write && (
                      <Button size="xs" variant="subtle" color="brique" onClick={() => removePayment.mutate(p.id)}
                        title={p.bank_transaction ? "Détache le virement du dossier ; son écriture est conservée" : undefined}>
                        {p.bank_transaction ? "Détacher" : "Supprimer"}</Button>)}</Table.Td>
                  </Table.Tr>))}
              </Table.Tbody>
            </Table>)}
          {can.write && <PaymentForm aid={aid} kinds={meta.payment_kinds} />}
          {can.write && (
            <Group>
              <ConfirmButton title={`Supprimer le dossier « ${aid.label} » ?`} message="Le dossier et ses versements saisis sont supprimés ; les écritures ne changent pas."
                confirmLabel="Supprimer" onConfirm={() => remove.mutateAsync(undefined).then(close)}>Supprimer le dossier</ConfirmButton>
            </Group>)}
        </Stack>)}
    </Drawer>
  );
}

export default function AidsPage() {
  const can = useCan();
  const [params, setParams] = useUrlParams({ campaign: String(new Date().getFullYear()) });
  const campaign = Number(params.campaign);
  const [dialog, setDialog] = useState<"new" | "pac" | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  const { data } = useQuery({ queryKey: [...AIDS_KEY, "list", campaign],
    queryFn: () => api.get<AidList>(`/api/v1/aids?campaign=${campaign}`) });
  if (!data) return <Center h={300}><Loader /></Center>;
  const { totals } = data;
  return (
    <>
      <PageHeader title="Aides et subventions"
        description="Dossiers d'aide par campagne : montants demandés, notifiés et versés, reste à percevoir et compte. Les versements restent comptabilisés par la banque."
        actions={can.write ? (
          <Group gap="xs">
            <Button variant="light" onClick={() => setDialog("pac")}>Nouvelle campagne PAC</Button>
            <Button onClick={() => setDialog("new")}>Nouveau dossier</Button>
          </Group>) : undefined} />
      <FilterBar>
        <Select aria-label="Campagne" w={160} allowDeselect={false} value={String(campaign)}
          data={data.meta.campaigns.map((y) => ({ value: String(y), label: `Campagne ${y}` }))}
          onChange={(v) => setParams({ campaign: v ?? "" })} />
      </FilterBar>
      <SimpleGrid cols={{ base: 1, sm: 3 }} mb="lg">
        <Paper withBorder p="md"><Text size="xs" c="dimmed">Acquis (notifié, sinon demandé)</Text><MoneyText cents={totals.acquired_cents} /></Paper>
        <Paper withBorder p="md"><Text size="xs" c="dimmed">Versé</Text><MoneyText cents={totals.paid_cents} /></Paper>
        <Paper withBorder p="md"><Text size="xs" c="dimmed">Reste à percevoir</Text><Title order={3}><MoneyText cents={totals.remaining_cents} /></Title></Paper>
      </SimpleGrid>
      {data.items.length === 0 ? (
        <Text c="dimmed">Aucun dossier pour la campagne {campaign}.{can.write && " Créez ceux de la campagne PAC d'après le profil de l'exploitation."}</Text>
      ) : (
        <Table highlightOnHover>
          <Table.Thead><Table.Tr><Table.Th>Dossier</Table.Th><Table.Th>Compte</Table.Th><Table.Th ta="right">Demandé</Table.Th>
            <Table.Th ta="right">Notifié</Table.Th><Table.Th ta="right">Versé</Table.Th><Table.Th ta="right">Reste</Table.Th><Table.Th>Statut</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {data.items.map((a) => (
              <Table.Tr key={a.id} style={{ cursor: "pointer" }} onClick={() => setOpenId(a.id)}>
                <Table.Td>{a.label}{a.warnings.map((w) => <Text key={w} size="xs" c="var(--lv-paille-ink)">{w}</Text>)}</Table.Td>
                <Table.Td><span className="lv-num">{a.account.code}</span>{a.operating_account && <> + <span className="lv-num">{a.operating_account.code}</span></>}</Table.Td>
                <Table.Td ta="right">{a.requested_cents !== null ? <MoneyText cents={a.requested_cents} /> : "—"}</Table.Td>
                <Table.Td ta="right">{a.notified_cents !== null ? <MoneyText cents={a.notified_cents} /> : "—"}</Table.Td>
                <Table.Td ta="right"><MoneyText cents={a.paid_cents} /></Table.Td>
                <Table.Td ta="right"><MoneyText cents={a.remaining_cents} /></Table.Td>
                <Table.Td><StatusBadge tone={TONES[a.status]}>{a.status_label}</StatusBadge></Table.Td>
              </Table.Tr>))}
          </Table.Tbody>
        </Table>)}
      <CapCheckCard year={campaign} />
      <FormModal opened={dialog === "new"} onClose={() => setDialog(null)} title="Nouveau dossier d'aide">
        {dialog === "new" && <NewAidForm campaign={campaign} onDone={() => setDialog(null)} />}
      </FormModal>
      <FormModal opened={dialog === "pac"} onClose={() => setDialog(null)} title={`Campagne PAC ${campaign}`}>
        {dialog === "pac" && <PacCampaignForm campaign={campaign} onDone={() => setDialog(null)} />}
      </FormModal>
      <AidDrawer aidId={openId} meta={data.meta} onClose={() => setOpenId(null)} />
    </>
  );
}
