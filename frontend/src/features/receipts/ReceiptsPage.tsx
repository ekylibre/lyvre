// Dons › Reçus fiscaux : par année civile, dons à reprendre par donateur (mentions manquantes
// signalées), lignes sans donateur à rattacher, émission en arrière-plan (annuelle ou par don,
// numéros définitifs), reçus émis (PDF, envoi par email, annulation et réémission), dons en nature,
// état annuel (synthèse, rapprochement avec les dons comptabilisés, export tableur).
import { useCallback, useState } from "react";
import {
  Alert, Anchor, Badge, Button, Center, Checkbox, Group, Loader, Paper, SegmentedControl, Select, SimpleGrid, Stack, Table,
  Tabs, Text, Textarea, TextInput,
} from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileText, Mail } from "lucide-react";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { confirmAction } from "../../components/ConfirmButton";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { FormModal } from "../../components/FormModal";
import { JobStatus, type Job } from "../../components/JobStatus";
import { MoneyInput, MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { useIntegrationGuard } from "../../components/IntegrationRequired";
import { formatDate, formatDateTime } from "../../lib/format";
import { AppLink } from "../../app/navigation";

interface Item { kind: "line" | "in_kind"; id: number; date: string; reference: string | null; entry_url: string | null;
  label: string; account: string | null; amount_cents: number; payment_method: string }
interface Donor { entity_id: number; name: string; person_kind: "individual" | "company" | null; email: string | null;
  problems: string[]; items: Item[]; total_cents: number }
interface Candidates { year: number; donors: Donor[]; unassigned: Item[]; total_cents: number; entities: { value: string; label: string }[] }
interface Receipt { id: number; number: string; donor: string; entity_id: number; person_kind: string; mode: string;
  total_cents: number; status: string; items: number; issued_at: string; sent_at: string | null; pdf_url: string;
  email: string | null; sent_to: string | null; cancel_reason: string | null; replaced_by: string | null }
interface Summary {
  year: number; issued: { count: number; amount_cents: number }; cancelled: { count: number; amount_cents: number };
  by_kind: Record<"individual" | "company", { count: number; amount_cents: number }>;
  by_nature: Record<string, { label: string; amount_cents: number }>; sent: number; unsent: number;
  booked_donations_cents: number; receipted_donations_cents: number; pending_donations_cents: number; export_url: string;
}
interface Gift { id: number; entity_id: number; donor: string; date: string; description: string; valuation_cents: number;
  valuation_method: string | null; receipted: boolean }

const KEY = ["receipts"];
const ISSUE_TITLES = { running: "Émission des reçus en cours…", done: "Émission terminée", failed: "L'émission a échoué" };
const SEND_TITLES = { running: "Envoi des reçus en cours…", done: "Envoi terminé", failed: "L'envoi a échoué" };
const KINDS = { individual: "Particulier", company: "Entreprise" } as const;

export default function ReceiptsPage() {
  const thisYear = new Date().getFullYear();
  const [params, setParams] = useUrlParams({ year: String(thisYear), tab: "pending" });
  const year = Number(params.year);
  const issued = useQuery({ queryKey: [...KEY, "issued", year],
    queryFn: () => api.get<{ items: Receipt[]; meta: { year: number; enabled: boolean } }>(`/api/v1/receipts?year=${year}`) });
  const years = Array.from({ length: 6 }, (_v, i) => String(thisYear - i));
  const client = useQueryClient();
  const [job, setJob] = useState<{ job: Job; titles: typeof ISSUE_TITLES } | null>(null);
  const refresh = useCallback(() => { void client.invalidateQueries({ queryKey: KEY }); }, [client]);
  return (
    <>
      <PageHeader title="Reçus fiscaux" description="Reçus des dons de l'année civile : particuliers (Cerfa 11580) et entreprises (Cerfa 16216)." />
      <FilterBar>
        <Select aria-label="Année" w={140} allowDeselect={false} data={years} value={params.year}
          onChange={(v) => setParams({ ...params, year: v ?? String(thisYear) })} />
      </FilterBar>
      {issued.data && !issued.data.meta.enabled && (
        <Alert color="paille" mb="md">Les reçus fiscaux ne sont pas activés :{" "}
          <Anchor component={AppLink} href="/configuration/receipts" size="sm">Configuration › Reçus fiscaux</Anchor>.</Alert>
      )}
      {job && <JobStatus key={job.job.id} job={job.job} titles={job.titles} onDone={refresh}
        renderResult={(r) => <JobResult result={r} />} />}
      <Tabs value={params.tab} onChange={(v) => setParams({ ...params, tab: v ?? "pending" })}>
        <Tabs.List mb="md">
          <Tabs.Tab value="pending">À émettre</Tabs.Tab>
          <Tabs.Tab value="issued">Reçus émis{issued.data ? ` (${issued.data.items.length})` : ""}</Tabs.Tab>
          <Tabs.Tab value="in-kind">Dons en nature</Tabs.Tab>
          <Tabs.Tab value="summary">État annuel</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="pending"><Pending year={year} enabled={issued.data?.meta.enabled ?? false}
          onJob={(j) => setJob({ job: j, titles: ISSUE_TITLES })} /></Tabs.Panel>
        <Tabs.Panel value="issued"><Issued year={year} receipts={issued.data?.items} onJob={(j) => setJob({ job: j, titles: SEND_TITLES })} /></Tabs.Panel>
        <Tabs.Panel value="in-kind"><InKind year={year} /></Tabs.Panel>
        <Tabs.Panel value="summary">{params.tab === "summary" && <AnnualSummary year={year} />}</Tabs.Panel>
      </Tabs>
    </>
  );
}

function JobResult({ result }: { result: Record<string, unknown> }) {
  const errors = (result.errors as string[] | undefined) ?? [];
  const parts = "issued" in result ? [`${result.issued} reçu(s) émis`, `${result.refused} donateur(s) à compléter`]
    : [`${result.sent} reçu(s) envoyé(s)`, `${result.skipped} sans adresse email`];
  return (
    <>
      <Text size="sm">{parts.join(", ")}.</Text>
      {errors.length > 0 && <Text size="xs" c="var(--lv-brique)">{errors.slice(0, 5).join(" · ")}{errors.length > 5 ? " …" : ""}</Text>}
    </>
  );
}

function Pending({ year, enabled, onJob }: { year: number; enabled: boolean; onJob: (job: Job) => void }) {
  const can = useCan();
  const { data } = useQuery({ queryKey: [...KEY, "candidates", year],
    queryFn: () => api.get<Candidates>(`/api/v1/receipts/candidates?year=${year}`) });
  const [selected, setSelected] = useState<number[]>([]);
  const [mode, setMode] = useState("annual");
  const issue = useAction((ids: number[]) => api.post<{ job: Job; notices?: Notice[] }>("/api/v1/receipts/issue", { year, entity_ids: ids, mode }));
  const assign = useAction(({ line, entity }: { line: number; entity: string | null }) =>
    api.put<{ notices: Notice[] }>(`/api/v1/receipts/lines/${line}/donor`, { entity_id: entity ? Number(entity) : null }),
    { invalidate: [[...KEY, "candidates", year]] });
  if (!data) return <Center h={200}><Loader /></Center>;
  const ready = data.donors.filter((d) => d.problems.length === 0);
  const chosen = selected.filter((id) => ready.some((d) => d.entity_id === id));
  const targets = chosen.length ? chosen : ready.map((d) => d.entity_id);
  const count = mode === "annual" ? targets.length
    : data.donors.filter((d) => targets.includes(d.entity_id)).reduce((s, d) => s + d.items.length, 0);
  const toggle = (id: number) => setSelected(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);
  return (
    <Stack>
      <Group justify="space-between">
        <Text size="sm">{data.donors.length} donateur(s) · <MoneyText cents={data.total_cents} size="sm" /> de dons à reprendre</Text>
        {can.write && enabled && (
          <Group>
            <SegmentedControl size="xs" value={mode} onChange={setMode}
              data={[{ value: "annual", label: "Reçu annuel" }, { value: "single", label: "Un reçu par don" }]} />
            <Button disabled={count === 0} loading={issue.isPending} onClick={() => confirmAction({
              title: `Émettre ${count} reçu(s) ${year} ?`, confirmLabel: "Émettre", danger: false,
              message: "Les numéros sont attribués définitivement et les PDF figés. Un reçu émis ne se supprime pas : il s'annule (motif) et se réémet.",
              onConfirm: () => issue.mutate(targets, { onSuccess: (body) => { setSelected([]); onJob(body.job); } }),
            })}>{chosen.length ? `Émettre la sélection (${count})` : `Émettre tout (${count})`}</Button>
          </Group>
        )}
      </Group>
      <Paper p={0} style={{ overflowX: "auto" }}>
        <Table verticalSpacing={6} miw={720}>
          <Table.Thead bg="var(--lv-sauge)"><Table.Tr><Table.Th w={40} /><Table.Th>Donateur</Table.Th><Table.Th>Nature</Table.Th>
            <Table.Th>Dons</Table.Th><Table.Th ta="right">Total</Table.Th><Table.Th>Reçu</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {data.donors.map((d) => (
              <Table.Tr key={d.entity_id}>
                <Table.Td>{can.write && <Checkbox aria-label={`Choisir ${d.name}`} disabled={d.problems.length > 0}
                  checked={selected.includes(d.entity_id)} onChange={() => toggle(d.entity_id)} />}</Table.Td>
                <Table.Td><Anchor component={AppLink} href={`/entities/${d.entity_id}`} size="sm">{d.name}</Anchor></Table.Td>
                <Table.Td>{d.person_kind ? <Badge variant="light" color="ardoise">{KINDS[d.person_kind]}</Badge> : "—"}</Table.Td>
                <Table.Td><Text size="sm">{d.items.map((i) => formatDate(i.date)).join(", ")}</Text></Table.Td>
                <Table.Td ta="right"><MoneyText cents={d.total_cents} size="sm" fw={600} /></Table.Td>
                <Table.Td>{d.problems.length
                  ? <Text size="sm" c="var(--lv-brique)">À compléter : {d.problems.join(", ")} ·{" "}
                    <Anchor component={AppLink} href={`/entities/${d.entity_id}/edit`} size="sm">fiche</Anchor></Text>
                  : <StatusBadge tone="ok">Prêt</StatusBadge>}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
        {data.donors.length === 0 && <Text size="sm" c="dimmed" p="md">Aucun don à reprendre pour {year}.</Text>}
      </Paper>
      {data.unassigned.length > 0 && (
        <>
          <Text fw={600} size="sm">Dons sans donateur identifié</Text>
          <Text size="xs" c="dimmed" mt={-12}>Le donateur est repris de la transaction bancaire ou du compte de tiers de l'écriture ; à défaut, choisissez-le ici.</Text>
          <Paper p={0}>
            <Table verticalSpacing={4}>
              <Table.Tbody>
                {data.unassigned.map((u) => (
                  <Table.Tr key={u.id}>
                    <Table.Td className="lv-num" w={100}>{formatDate(u.date)}</Table.Td>
                    <Table.Td><Anchor component={AppLink} href={u.entry_url ?? "#"} size="sm" className="lv-num">{u.reference}</Anchor></Table.Td>
                    <Table.Td><Text size="sm">{u.label}</Text></Table.Td>
                    <Table.Td ta="right"><MoneyText cents={u.amount_cents} size="sm" /></Table.Td>
                    <Table.Td w={260}>{can.write && <Select size="xs" aria-label={`Donateur du don du ${formatDate(u.date)}`} placeholder="Choisir le donateur"
                      searchable data={data.entities} onChange={(v) => assign.mutate({ line: u.id, entity: v })} />}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Paper>
        </>
      )}
    </Stack>
  );
}

function Issued({ year, receipts, onJob }: { year: number; receipts: Receipt[] | undefined; onJob: (job: Job) => void }) {
  const can = useCan();
  const [cancelling, setCancelling] = useState<Receipt | null>(null);
  const send = useAction((body: { ids?: number[]; year?: number }) =>
    api.post<{ job?: Job; notices?: Notice[] }>("/api/v1/receipts/send", body));
  const smtp = useIntegrationGuard("smtp", "L'envoi des reçus par email");
  const start = (body: { ids?: number[]; year?: number }) => send.mutate(body, { onSuccess: (r) => { if (r.job) onJob(r.job); } });
  if (!receipts) return <Center h={200}><Loader /></Center>;
  const unsent = receipts.filter((r) => r.status === "issued" && !r.sent_at && r.email).length;
  return (
    <Stack>
      {can.write && unsent > 0 && (
        <Group justify="flex-end">
          <Button variant="default" leftSection={<Mail size={16} />} loading={send.isPending}
            onClick={smtp.guard(() => confirmAction({ title: `Envoyer ${unsent} reçu(s) par email ?`, confirmLabel: "Envoyer", danger: false,
              message: "Chaque donateur reçoit son reçu en pièce jointe, à l'adresse email de sa fiche.",
              onConfirm: () => start({ year }) }))}>Envoyer les reçus non envoyés ({unsent})</Button>
        </Group>
      )}
      <Paper p={0} style={{ overflowX: "auto" }}>
        <Table verticalSpacing={6} miw={820}>
          <Table.Thead bg="var(--lv-sauge)"><Table.Tr><Table.Th>Numéro</Table.Th><Table.Th>Émis le</Table.Th><Table.Th>Donateur</Table.Th>
            <Table.Th>Type</Table.Th><Table.Th ta="right">Montant</Table.Th><Table.Th>Statut</Table.Th><Table.Th>Envoi</Table.Th><Table.Th /></Table.Tr></Table.Thead>
          <Table.Tbody>
            {receipts.map((r) => (
              <Table.Tr key={r.id} style={{ opacity: r.status === "issued" ? 1 : 0.65 }}>
                <Table.Td className="lv-num" fw={600}>{r.number}</Table.Td>
                <Table.Td className="lv-num">{formatDateTime(r.issued_at)}</Table.Td>
                <Table.Td><Anchor component={AppLink} href={`/entities/${r.entity_id}`} size="sm">{r.donor}</Anchor></Table.Td>
                <Table.Td><Text size="sm">{r.mode === "annual" ? `Annuel (${r.items} don${r.items > 1 ? "s" : ""})` : "Don unique"} ·{" "}
                  {KINDS[r.person_kind as keyof typeof KINDS]}</Text></Table.Td>
                <Table.Td ta="right"><MoneyText cents={r.total_cents} size="sm" /></Table.Td>
                <Table.Td>{r.status === "issued" ? <StatusBadge tone="ok">Émis</StatusBadge> : (
                  <Stack gap={0}><StatusBadge tone="neutral">Annulé</StatusBadge>
                    <Text size="xs" c="dimmed">{r.cancel_reason}{r.replaced_by && ` · remplacé par ${r.replaced_by}`}</Text></Stack>)}</Table.Td>
                <Table.Td><Text size="xs" c="dimmed">{r.sent_at ? `${formatDate(r.sent_at)} · ${r.sent_to}` : r.email ? "Non envoyé" : "Sans email"}</Text></Table.Td>
                <Table.Td ta="right" style={{ whiteSpace: "nowrap" }}>
                  <Button variant="subtle" size="compact-sm" component="a" href={r.pdf_url} target="_blank" leftSection={<FileText size={14} />}>PDF</Button>
                  {can.write && r.status === "issued" && r.email && <Button variant="subtle" size="compact-sm" onClick={smtp.guard(() => start({ ids: [r.id] }))}>
                    {r.sent_at ? "Renvoyer" : "Envoyer"}</Button>}
                  {can.write && r.status === "issued" && <Button variant="subtle" size="compact-sm" color="brique" onClick={() => setCancelling(r)}>Annuler…</Button>}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
        {receipts.length === 0 && <Text size="sm" c="dimmed" p="md">Aucun reçu émis pour cette année.</Text>}
      </Paper>
      <FormModal opened={!!cancelling} onClose={() => setCancelling(null)} title={`Annuler le reçu ${cancelling?.number ?? ""}`}>
        {cancelling && <CancelForm receipt={cancelling} onDone={() => setCancelling(null)} />}
      </FormModal>
    </Stack>
  );
}

function CancelForm({ receipt, onDone }: { receipt: Receipt; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const [reissue, setReissue] = useState(true);
  const cancel = useAction(() => api.post<{ notices: Notice[] }>(`/api/v1/receipts/${receipt.id}/cancel`, { reason, reissue }),
    { invalidate: [KEY] });
  return (
    <Stack>
      <Text size="sm">Le reçu reste conservé, marqué « annulé » avec son motif ; son numéro n'est jamais réutilisé.
        Pensez à prévenir {receipt.donor} que le reçu {receipt.number} n'est plus valable.</Text>
      <Textarea label="Motif" required autosize minRows={2} value={reason} onChange={(e) => setReason(e.currentTarget.value)} data-autofocus />
      <Checkbox label="Émettre aussitôt un reçu de remplacement pour les mêmes dons (adresse du donateur à jour)"
        checked={reissue} onChange={(e) => setReissue(e.currentTarget.checked)} />
      <Group justify="flex-end">
        <Button variant="default" onClick={onDone}>Retour</Button>
        <Button color="brique" loading={cancel.isPending} disabled={reason.trim().length < 5}
          onClick={() => cancel.mutate(undefined, { onSuccess: onDone })}>{reissue ? "Annuler et réémettre" : "Annuler le reçu"}</Button>
      </Group>
    </Stack>
  );
}

function AnnualSummary({ year }: { year: number }) {
  const { data } = useQuery({ queryKey: [...KEY, "summary", year], queryFn: () => api.get<Summary>(`/api/v1/receipts/summary?year=${year}`) });
  if (!data) return <Center h={200}><Loader /></Center>;
  const consistent = data.receipted_donations_cents + data.pending_donations_cents === data.booked_donations_cents;
  return (
    <Stack>
      <Group justify="flex-end"><Button variant="default" component="a" href={data.export_url} leftSection={<Download size={16} />}>Exporter (XLSX)</Button></Group>
      <SimpleGrid cols={{ base: 1, sm: 3 }}>
        <Paper p="md"><Text size="sm" c="dimmed">Reçus émis</Text>
          <Text fz={24} fw={500} className="lv-num">{data.issued.count}</Text><MoneyText cents={data.issued.amount_cents} /></Paper>
        <Paper p="md"><Text size="sm" c="dimmed">Particuliers / entreprises</Text>
          <Text className="lv-num">{data.by_kind.individual.count} · <MoneyText cents={data.by_kind.individual.amount_cents} /></Text>
          <Text className="lv-num">{data.by_kind.company.count} · <MoneyText cents={data.by_kind.company.amount_cents} /></Text></Paper>
        <Paper p="md"><Text size="sm" c="dimmed">Reçus annulés · envoyés</Text>
          <Text className="lv-num">{data.cancelled.count} annulé(s) · <MoneyText cents={data.cancelled.amount_cents} /></Text>
          <Text className="lv-num">{data.sent} envoyé(s), {data.unsent} non envoyé(s)</Text></Paper>
      </SimpleGrid>
      <Paper p={0}>
        <Table verticalSpacing={6}>
          <Table.Tbody>
            <Table.Tr><Table.Td>Dons comptabilisés en {year} (comptes de dons)</Table.Td><Table.Td ta="right"><MoneyText cents={data.booked_donations_cents} fw={600} /></Table.Td></Table.Tr>
            <Table.Tr><Table.Td>dont repris sur un reçu émis</Table.Td><Table.Td ta="right"><MoneyText cents={data.receipted_donations_cents} /></Table.Td></Table.Tr>
            <Table.Tr><Table.Td>dont encore à reprendre (y compris sans donateur)</Table.Td><Table.Td ta="right"><MoneyText cents={data.pending_donations_cents} /></Table.Td></Table.Tr>
            {Object.entries(data.by_nature).map(([key, n]) => (
              <Table.Tr key={key}><Table.Td>Reçus émis — {n.label}</Table.Td><Table.Td ta="right"><MoneyText cents={n.amount_cents} /></Table.Td></Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Paper>
      {!consistent && <Alert color="brique">Écart entre les dons comptabilisés et les reçus : vérifiez les dons rattachés à un reçu puis modifiés.</Alert>}
      <Text size="xs" c="dimmed">Ces chiffres servent à la déclaration annuelle du montant global des dons et du nombre de reçus délivrés.</Text>
    </Stack>
  );
}

function InKind({ year }: { year: number }) {
  const can = useCan();
  const { data } = useQuery({ queryKey: [...KEY, "in-kind", year], queryFn: () => api.get<{ items: Gift[] }>(`/api/v1/receipts/in-kind?year=${year}`) });
  const entities = useQuery({ queryKey: [...KEY, "candidates", year], queryFn: () => api.get<Candidates>(`/api/v1/receipts/candidates?year=${year}`) });
  const [adding, setAdding] = useState(false);
  const remove = useAction((id: number) => api.delete<{ notices: Notice[] }>(`/api/v1/receipts/in-kind/${id}`), { invalidate: [KEY] });
  if (!data) return <Center h={200}><Loader /></Center>;
  return (
    <Stack>
      <Group justify="space-between">
        <Text size="sm" c="dimmed">Biens ou prestations donnés, valorisés par l'association. Ils sont repris sur le reçu du donateur ; leur comptabilisation (86 / 87 ou charge / produit) se fait à part.</Text>
        {can.write && <Button variant="default" onClick={() => setAdding(true)}>Ajouter un don en nature</Button>}
      </Group>
      <Paper p={0}>
        <Table verticalSpacing={4}>
          <Table.Tbody>
            {data.items.map((g) => (
              <Table.Tr key={g.id}>
                <Table.Td className="lv-num" w={100}>{formatDate(g.date)}</Table.Td>
                <Table.Td><Text size="sm">{g.donor}</Text></Table.Td>
                <Table.Td><Text size="sm">{g.description}{g.valuation_method && <Text span size="xs" c="dimmed"> · {g.valuation_method}</Text>}</Text></Table.Td>
                <Table.Td ta="right"><MoneyText cents={g.valuation_cents} size="sm" /></Table.Td>
                <Table.Td w={140} ta="right">{g.receipted ? <StatusBadge tone="ok">Sur un reçu</StatusBadge>
                  : can.write && <Button variant="subtle" size="compact-sm" color="brique" onClick={() => confirmAction({
                    title: `Supprimer « ${g.description} » ?`, confirmLabel: "Supprimer", onConfirm: () => remove.mutate(g.id) })}>Supprimer</Button>}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
        {data.items.length === 0 && <Text size="sm" c="dimmed" p="md">Aucun don en nature pour cette année.</Text>}
      </Paper>
      <FormModal opened={adding} onClose={() => setAdding(false)} title="Ajouter un don en nature">
        {adding && <InKindForm year={year} entities={entities.data?.entities ?? []} onDone={() => setAdding(false)} />}
      </FormModal>
    </Stack>
  );
}

function InKindForm({ year, entities, onDone }: { year: number; entities: { value: string; label: string }[]; onDone: () => void }) {
  const [entity, setEntity] = useState<string | null>(null);
  const [when, setWhen] = useState<string | null>(null);
  const [description, setDescription] = useState("");
  const [value, setValue] = useState<number | null>(null);
  const [method, setMethod] = useState("");
  const save = useAction(() => api.post<{ notices: Notice[] }>("/api/v1/receipts/in-kind", {
    entity_id: entity ? Number(entity) : null, date: when, description, valuation_cents: value, valuation_method: method,
  }), { invalidate: [KEY] });
  return (
    <Stack>
      <Select label="Donateur" required searchable data={entities} value={entity} onChange={setEntity} data-autofocus />
      <DateInput label="Date du don" required valueFormat="DD/MM/YYYY" value={when} onChange={setWhen}
        minDate={`${year}-01-01`} maxDate={`${year}-12-31`} />
      <TextInput label="Description" required placeholder="Ordinateur portable, lot de livres…" value={description}
        onChange={(e) => setDescription(e.currentTarget.value)} />
      <MoneyInput label="Valorisation" required value={value} onChange={setValue} />
      <TextInput label="Méthode de valorisation" placeholder="Valeur de marché, valeur nette comptable…" value={method}
        onChange={(e) => setMethod(e.currentTarget.value)} />
      <Group justify="flex-end">
        <Button variant="default" onClick={onDone}>Annuler</Button>
        <Button loading={save.isPending} disabled={!entity || !when || !description.trim() || !value}
          onClick={() => save.mutate(undefined, { onSuccess: onDone })}>Enregistrer</Button>
      </Group>
    </Stack>
  );
}
