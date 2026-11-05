// Compta › Échéancier (lot AG9a.b, claudedocs/design_echeancier_agricole.md § 5) : échéances de l'exploitation en
// liste (en retard, cette semaine, à préparer, à venir, faites) ou en calendrier mensuel ; fiche de chaque échéance
// (organisme, ce qu'il faut préparer, pénalités, lien officiel, fiabilité) ; marquer faite ou ignorée.
import { useMemo, useState } from "react";
import {
  ActionIcon, Alert, Anchor, Badge, Button, Center, CopyButton, Drawer, Group, List, Loader, Modal, MultiSelect, Paper,
  SegmentedControl,
  SimpleGrid, Stack, Switch, Table, Text, TextInput, Title,
} from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { AppLink } from "../../app/navigation";
import { formatDate } from "../../lib/format";
import { RELIABILITY_COLORS } from "../organization/FiscalProfile";
import { ExplainButton } from "../assistant/AssistantDrawer";
import { ChecklistsPanel } from "./ChecklistsPanel";
import {
  AGENDA_KEY, BLOCKS, DOMAIN_COLORS, STATUS_TONES, type AgendaResponse, type AgendaSubscription, type BankDebit, type Detection,
  type Occurrence,
} from "./types";

const WEEKDAYS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."];
const pad = (n: number) => String(n).padStart(2, "0");
const isoOf = (y: number, m: number, d: number) => `${y}-${pad(m + 1)}-${pad(d)}`;

function statusLabel(occ: Occurrence, labels: Record<string, string>) {
  return occ.status === "ready" ? "Prête (validée dans Lyvre)" : labels[occ.status];
}

function DebitLine({ debit }: { debit: BankDebit }) {
  return (
    <Text size="sm">{formatDate(debit.date)} · {debit.label} · <MoneyText cents={debit.amount_cents} />{" "}
      <Anchor component={AppLink} href={`/bank-accounts/${debit.bank_account_id}/transactions`} size="sm">relevé</Anchor></Text>
  );
}

/** Débits de l'organisme à J-10/J+10, pour rattacher le paiement à la main (lot AG9a.c). */
function PaymentCandidates({ occ, onDone }: { occ: Occurrence; onDone: () => void }) {
  const query = new URLSearchParams({ deadline_id: occ.deadline_id, occurs_on: occ.date, period: occ.period });
  const { data } = useQuery({
    queryKey: [...AGENDA_KEY, "candidates", occ.key],
    queryFn: () => api.get<{ items: BankDebit[] }>(`/api/v1/agenda/candidates?${query}`),
  });
  const link = useAction((id: number) => api.post<{ notices: Notice[] }>("/api/v1/agenda/states",
    { deadline_id: occ.deadline_id, occurs_on: occ.date, period: occ.period, status: "done", bank_transaction_id: id }),
  { invalidate: [AGENDA_KEY] });
  if (!data) return null;
  return (
    <Stack gap={4}>
      <Text size="sm" fw={600}>Paiement sur les relevés</Text>
      {occ.unlinked && <Text size="xs" c="dimmed">Paiement détaché : Lyvre ne le rattache plus automatiquement.</Text>}
      {data.items.length === 0 ? <Text size="sm" c="dimmed">Aucun débit de l'organisme du {formatDate(occ.date)} à 10 jours près.</Text>
        : data.items.map((d) => (
          <Group key={d.id} gap="xs" wrap="nowrap">
            <DebitLine debit={d} />
            {d.amount_matches && <Badge size="xs" color="lichen" variant="light">montant attendu</Badge>}
            <Button size="compact-xs" variant="light" loading={link.isPending}
              onClick={() => link.mutate(d.id, { onSuccess: onDone })}>Rattacher</Button>
          </Group>))}
    </Stack>
  );
}

function OccurrenceDrawer({ occ, data, onClose }: { occ: Occurrence | null; data: AgendaResponse; onClose: () => void }) {
  const can = useCan();
  const [note, setNote] = useState("");
  const opts = { invalidate: [AGENDA_KEY] };
  const mark = useAction((status: "done" | "skipped") => api.post<{ notices: Notice[] }>("/api/v1/agenda/states",
    { deadline_id: occ!.deadline_id, occurs_on: occ!.date, period: occ!.period, status, note }), opts);
  const clear = useAction((id: number) => api.delete<{ notices: Notice[] }>(`/api/v1/agenda/states/${id}`), opts);
  const fiche = occ ? data.fiches[occ.fiche_id] : null;
  const labels = Object.fromEntries(data.statuses.map((s) => [s.value, s.label]));
  return (
    <Drawer opened={!!occ} onClose={onClose} position="right" size="lg" title={occ ? `${occ.label} — ${formatDate(occ.date)}` : ""}>
      {occ && fiche && (
        <Stack>
          <Group gap="xs">
            <StatusBadge tone={STATUS_TONES[occ.status]}>{statusLabel(occ, labels)}</StatusBadge>
            <Badge variant="light" color={DOMAIN_COLORS[fiche.domain]}>{fiche.domain_label}</Badge>
            <Badge variant="light" color={RELIABILITY_COLORS[occ.reliability]}>fiabilité {occ.reliability}</Badge>
            {occ.to_confirm && <Badge color="paille">date à confirmer</Badge>}
          </Group>
          <Text size="sm"><b>{fiche.title}</b> — {fiche.organism} · {occ.period}</Text>
          {occ.edi_date && <Text size="sm">Télédéclaration (EDI) : jusqu'au {formatDate(occ.edi_date)}.</Text>}
          {occ.amount_cents !== null && <Text size="sm">Montant {occ.amount_proposed ? "calculé par Lyvre" : "enregistré"} :{" "}
            <MoneyText cents={occ.amount_cents} /></Text>}
          <Text size="sm">{fiche.summary}</Text>
          {fiche.prepare && fiche.prepare.length > 0 && <><Text size="sm" fw={600}>À préparer</Text>
            <List size="sm">{fiche.prepare.map((p) => <List.Item key={p}>{p}</List.Item>)}</List></>}
          {fiche.lyvre_data && <Text size="sm"><b>Dans Lyvre :</b> {fiche.lyvre_data}</Text>}
          {fiche.penalties && <Text size="sm"><b>Pénalités :</b> {fiche.penalties}</Text>}
          {fiche.links?.map((l) => <Anchor key={l} size="sm" href={l} target="_blank" rel="noreferrer">{l}</Anchor>)}
          {fiche.reminder_only && <Text size="xs" c="dimmed">Démarche hors comptabilité : Lyvre la rappelle seulement.</Text>}
          <Group>
            {occ.status === "late" && <ExplainButton label="Que faire ?" question={`Échéance en retard : ${occ.title} — ${occ.label} du ${formatDate(occ.date)} (${occ.organism}). Que dois-je faire maintenant, avec quelle pénalité ?`} />}
            {occ.action?.route && <Button component={AppLink} href={occ.link ?? occ.action.route}>{occ.action.label}</Button>}
            {occ.action?.url && <Button component="a" href={occ.action.url} target="_blank" rel="noreferrer">{occ.action.label}</Button>}
          </Group>
          {occ.state?.origin === "bank" && occ.state.transaction ? (
            <Stack gap={4}>
              <Text size="sm" fw={600}>Paiement reconnu sur les relevés</Text>
              <DebitLine debit={occ.state.transaction} />
              {can.write && <Group><Button variant="subtle" size="xs" onClick={() => clear.mutate(occ.state!.id, { onSuccess: onClose })}>
                Détacher le paiement</Button></Group>}
            </Stack>
          ) : occ.state ? (can.write && (
            <Group><Text size="sm">{occ.state.status === "done" ? `Faite le ${formatDate(occ.state.done_on)}` : `Ignorée : ${occ.state.note}`}</Text>
              <Button variant="subtle" size="xs" onClick={() => clear.mutate(occ.state!.id, { onSuccess: onClose })}>Remettre à faire</Button></Group>
          )) : (<>
            {occ.payment && occ.status !== "done" && can.write && <PaymentCandidates occ={occ} onDone={onClose} />}
            {occ.managed ? <Text size="xs" c="dimmed">Échéance suivie par Lyvre : elle passe à « faite » au dépôt de la déclaration.</Text>
              : can.write && (
              <Stack gap="xs">
                <TextInput label="Remarque" description="Obligatoire pour ignorer une échéance." value={note}
                  onChange={(e) => setNote(e.currentTarget.value)} />
                <Group>
                  <Button onClick={() => mark.mutate("done", { onSuccess: onClose })} loading={mark.isPending}>Marquer faite</Button>
                  <Button variant="light" disabled={!note.trim()} onClick={() => mark.mutate("skipped", { onSuccess: onClose })}>Ignorer</Button>
                </Group>
              </Stack>)}
          </>)}
        </Stack>)}
    </Drawer>
  );
}

function ListView({ items, data, onOpen }: { items: Occurrence[]; data: AgendaResponse; onOpen: (o: Occurrence) => void }) {
  const labels = Object.fromEntries(data.statuses.map((s) => [s.value, s.label]));
  return (
    <Stack>
      {BLOCKS.map((block) => {
        const rows = items.filter((o) => block.status.includes(o.status) && !(o.quiet && o.status === "upcoming"));
        if (rows.length === 0) return null;
        return (
          <Paper key={block.title} withBorder p="md">
            <Title order={4} mb="xs">{block.title} <Text span c="dimmed" size="sm">({rows.length})</Text></Title>
            <Table highlightOnHover>
              <Table.Tbody>
                {rows.map((o) => (
                  <Table.Tr key={o.key} style={{ cursor: "pointer" }} onClick={() => onOpen(o)}>
                    <Table.Td w={110} className="lv-num">{formatDate(o.date)}</Table.Td>
                    <Table.Td>{o.label}{o.to_confirm && <Badge ml="xs" size="xs" color="paille">à confirmer</Badge>}
                      <Text size="xs" c="dimmed">{data.fiches[o.fiche_id]?.organism} · {o.period}</Text></Table.Td>
                    <Table.Td w={150}><Badge variant="light" color={DOMAIN_COLORS[o.domain]}>{data.fiches[o.fiche_id]?.domain_label}</Badge></Table.Td>
                    <Table.Td w={130} ta="right">{o.amount_cents !== null ? <MoneyText cents={o.amount_cents} /> : ""}</Table.Td>
                    <Table.Td w={170}><StatusBadge tone={STATUS_TONES[o.status]}>{statusLabel(o, labels)}</StatusBadge></Table.Td>
                  </Table.Tr>))}
              </Table.Tbody>
            </Table>
          </Paper>);
      })}
    </Stack>
  );
}

function CalendarView({ items, today, onOpen }: { items: Occurrence[]; today: string; onOpen: (o: Occurrence) => void }) {
  const [month, setMonth] = useState(() => { const [y, m] = today.split("-").map(Number); return { y, m: m - 1 }; });
  const first = new Date(month.y, month.m, 1);
  const offset = (first.getDay() + 6) % 7;
  const days = new Date(month.y, month.m + 1, 0).getDate();
  const byDay = useMemo(() => {
    const map: Record<string, Occurrence[]> = {};
    for (const o of items) (map[o.date] ??= []).push(o);
    return map;
  }, [items]);
  const shift = (n: number) => setMonth(({ y, m }) => ({ y: m + n < 0 ? y - 1 : m + n > 11 ? y + 1 : y, m: (m + n + 12) % 12 }));
  const cells = [...Array(offset).fill(null), ...Array.from({ length: days }, (_, i) => i + 1)];
  return (
    <Paper withBorder p="md">
      <Group justify="space-between" mb="sm">
        <ActionIcon variant="subtle" aria-label="Mois précédent" onClick={() => shift(-1)}><ChevronLeft size={18} /></ActionIcon>
        <Title order={4}>{first.toLocaleDateString("fr-FR", { month: "long", year: "numeric" })}</Title>
        <ActionIcon variant="subtle" aria-label="Mois suivant" onClick={() => shift(1)}><ChevronRight size={18} /></ActionIcon>
      </Group>
      <SimpleGrid cols={7} spacing={4}>
        {WEEKDAYS.map((d) => <Text key={d} size="xs" c="dimmed" ta="center">{d}</Text>)}
        {cells.map((day, i) => {
          if (day === null) return <div key={`blank-${i}`} />;
          const iso = isoOf(month.y, month.m, day);
          return (
            <Paper key={iso} withBorder p={4} mih={84} bg={iso === today ? "var(--mantine-color-lichen-0)" : undefined}>
              <Text size="xs" c="dimmed">{day}</Text>
              <Stack gap={2}>
                {(byDay[iso] ?? []).map((o) => (
                  <Badge key={o.key} size="xs" fullWidth radius="sm" style={{ cursor: "pointer", textTransform: "none" }}
                    variant={o.status === "done" || o.status === "skipped" ? "outline" : "light"}
                    color={o.status === "late" ? "brique" : DOMAIN_COLORS[o.domain]} onClick={() => onOpen(o)}>{o.label}</Badge>))}
              </Stack>
            </Paper>);
        })}
      </SimpleGrid>
    </Paper>
  );
}

/** Points à vérifier : changement de régime, crédit de TVA, options, relevés, dates à confirmer, profil (§ 6.2). */
function Detections({ items }: { items: Detection[] }) {
  if (items.length === 0) return null;
  return (
    <Paper withBorder p="md" mb="md">
      <Title order={4} mb="xs">À vérifier</Title>
      <Stack gap="sm">
        {items.map((d) => (
          <div key={d.id}>
            <Group gap="xs">
              <StatusBadge tone={d.level === "warning" ? "todo" : "info"}>{d.level === "warning" ? "À traiter" : "Pour information"}</StatusBadge>
              <Text size="sm" fw={600}>{d.title}</Text>
            </Group>
            <Text size="sm">{d.detail}{" "}
              {d.link && <Anchor component={AppLink} href={d.link} size="sm">{d.link_label ?? "Ouvrir"}</Anchor>}</Text>
          </div>))}
      </Stack>
    </Paper>
  );
}

/** Abonnement au résumé du lundi par e-mail (lot AG9a.d) ; pas pour l'expert-comptable en lecture seule. */
function SubscriptionSwitch() {
  const { data } = useQuery({
    queryKey: [...AGENDA_KEY, "subscription"],
    queryFn: () => api.get<{ item: AgendaSubscription }>("/api/v1/agenda/subscription"),
  });
  const save = useAction((subscribed: boolean) => api.put<{ notices: Notice[] }>("/api/v1/agenda/subscription", { subscribed }),
    { invalidate: [[...AGENDA_KEY, "subscription"]] });
  const sub = data?.item;
  if (!sub?.available) return null;
  return (
    <Switch label="Résumé du lundi par e-mail" description={sub.email} checked={sub.subscribed} disabled={save.isPending}
      onChange={(e) => save.mutate(e.currentTarget.checked)} />
  );
}

/** Adresse secrète du calendrier iCal (lot AG9a.e), à coller dans un logiciel d'agenda. */
function IcalButton() {
  const [opened, setOpened] = useState(false);
  const key = [...AGENDA_KEY, "ical"];
  const { data } = useQuery({ queryKey: key, queryFn: () => api.get<{ item: { url: string | null } }>("/api/v1/agenda/ical"),
    enabled: opened });
  const create = useAction(() => api.post<{ notices: Notice[] }>("/api/v1/agenda/ical", {}), { invalidate: [key] });
  const revoke = useAction(() => api.delete<{ notices: Notice[] }>("/api/v1/agenda/ical"), { invalidate: [key] });
  const can = useCan();
  const url = data?.item.url ?? null;
  return (
    <>
      <Button variant="light" onClick={() => setOpened(true)}>Agenda (iCal)</Button>
      <Modal opened={opened} onClose={() => setOpened(false)} title="Échéancier dans votre agenda" size="lg">
        <Stack>
          <Text size="sm">Abonnez votre agenda (Google Agenda, Outlook, Calendrier d'Apple, Thunderbird) à cette adresse :
            les échéances des 30 derniers jours et des 13 prochains mois s'y affichent et se mettent à jour d'elles-mêmes.</Text>
          <Text size="sm" c="dimmed">L'adresse est personnelle : toute personne qui la connaît voit l'échéancier. Régénérez-la si
            elle a circulé ; l'ancienne cessera de fonctionner.</Text>
          {url ? (<>
            <Group gap="xs" wrap="nowrap">
              <TextInput aria-label="Adresse du calendrier" readOnly value={url} style={{ flex: 1 }}
                onFocus={(e) => e.currentTarget.select()} />
              <CopyButton value={url}>{({ copied, copy }) => (
                <Button variant="light" onClick={copy}>{copied ? "Copiée" : "Copier"}</Button>)}</CopyButton>
            </Group>
            {can.write && <Group>
              <Button variant="subtle" loading={create.isPending} onClick={() => create.mutate()}>Régénérer l'adresse</Button>
              <Button variant="subtle" color="brique" loading={revoke.isPending} onClick={() => revoke.mutate()}>Révoquer</Button>
            </Group>}
          </>) : can.write ? (
            <Group><Button loading={create.isPending} onClick={() => create.mutate()}>Créer l'adresse du calendrier</Button></Group>
          ) : <Text size="sm">Aucune adresse de calendrier.</Text>}
        </Stack>
      </Modal>
    </>
  );
}

export default function AgendaPage() {
  const [params, setParams] = useUrlParams({ view: "list", domains: "" });
  const [open, setOpen] = useState<Occurrence | null>(null);
  const { data } = useQuery({ queryKey: AGENDA_KEY, queryFn: () => api.get<AgendaResponse>("/api/v1/agenda") });
  if (!data) return <Center h={300}><Loader /></Center>;
  const domains = params.domains ? params.domains.split(",") : [];
  const items = data.items.filter((o) => domains.length === 0 || domains.includes(o.domain));
  return (
    <>
      <PageHeader title="Échéancier"
        description="Déclarations, paiements et démarches de l'exploitation, calculés depuis son profil et sa comptabilité. Lyvre ne télédéclare pas : il rappelle et prépare."
        actions={<Group><IcalButton /><SubscriptionSwitch /></Group>} />
      <Detections items={data.detections ?? []} />
      <ChecklistsPanel />
      {data.questions.length > 0 && (
        <Alert color="paille" mb="md" title={`${data.questions.length} démarche${data.questions.length > 1 ? "s" : ""} à préciser`}>
          Êtes-vous concerné par : {data.questions.map((id) => data.fiches[id]?.title).filter(Boolean).join(" ; ")} ?{" "}
          <Anchor component={AppLink} href="/configuration/organization?tab=activities">Répondre dans Activités et démarches</Anchor>
        </Alert>)}
      <FilterBar>
        <SegmentedControl value={params.view} onChange={(v) => setParams({ view: v })}
          data={[{ value: "list", label: "Liste" }, { value: "calendar", label: "Calendrier" }]} />
        <MultiSelect aria-label="Domaines" placeholder="Tous les domaines" w={360} clearable data={data.domains}
          value={domains} onChange={(v) => setParams({ domains: v.join(",") })} />
      </FilterBar>
      {params.view === "calendar" ? <CalendarView items={items} today={data.today} onOpen={setOpen} />
        : <ListView items={items} data={data} onOpen={setOpen} />}
      <OccurrenceDrawer occ={open} data={data} onClose={() => setOpen(null)} />
    </>
  );
}
