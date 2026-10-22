// Compta › Exercices › Clôture : assistant en étapes (GET /api/v1/fiscal-years/<id>/closing).
// Contrôles, écritures d'inventaire, fonds dédiés, résultat, FEC à blanc, puis clôture
// provisoire (trésorier, admin), définitive et réouverture (admin) ; ensuite à-nouveaux et
// extournes dans l'exercice suivant, et affectation du résultat. Les étapes 1 à 5 sont faites ou
// ignorées avec un motif ; l'expert-comptable consulte sans agir.
import { useState } from "react";
import { useParams } from "react-router";
import {
  ActionIcon, Alert, Anchor, Autocomplete, Button, Center, Grid, Group, List, Loader, NavLink, Paper, Select, SimpleGrid,
  Stack, Table, Text, Textarea, TextInput, Title,
} from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { AccountSelect } from "../../components/AccountSelect";
import { confirmAction } from "../../components/ConfirmButton";
import { FormModal } from "../../components/FormModal";
import { MoneyInput, MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge, type Tone } from "../../components/StatusBadge";
import { formatDate, formatDateTime } from "../../lib/format";
import type { Account } from "../../lib/types";
import { AppLink } from "../../app/navigation";
import { FecPanel } from "./FecPanel";
import { FISCAL_YEARS_KEY, type FiscalYear } from "./FiscalYearsPage";

type StepState = "todo" | "done" | "skipped" | "provisional";

interface Step { key: string; label: string; state: StepState; note: string | null; updated_at: string | null; available: boolean }
interface Check { key: string; label: string; count: number; severity: "anomaly" | "info"; url: string | null }
interface InventoryEntry {
  id: number; reference: string; kind: string; kind_label: string; description: string; amount_cents: number;
  lines: { account: string; debit_cents: number; credit_cents: number }[];
}
interface InventoryOption { label: string; classes: string[]; counterparts: { value: string; label: string }[] }
interface ClosingEvent { at: string; step: string | null; action: string; details: Record<string, unknown> | null }
interface ClosingView {
  fiscal_year: FiscalYear; steps: Step[]; checks: Check[]; inventory: InventoryEntry[];
  inventory_options: Record<string, InventoryOption>;
  result: { income_cents: number; expense_cents: number; result_cents: number };
  next_fiscal_year: FiscalYear | null; events: ClosingEvent[];
  opening: {
    lines: { account_code: string; label: string; debit_cents: number; credit_cents: number }[];
    error: string | null; reversals_planned: number; next_start_date: string;
    entries: (EntryLink & { source: string; description: string })[];
  };
  allocation: {
    result_cents: number; decided_on: string | null; body: string | null; entry: EntryLink | null;
    options: { value: string; label: string }[];
  };
}
interface EntryLink { id: number; reference: string; url: string }

const STATES: Record<StepState, [string, Tone]> = {
  todo: ["À faire", "todo"], done: ["Fait", "ok"], skipped: ["Ignorée", "neutral"], provisional: ["Provisoire", "info"],
};
const ACTIONS: Record<string, string> = {
  step_done: "Étape faite", step_skipped: "Étape ignorée", step_todo: "Étape remise à faire", add: "Écriture ajoutée",
  generate: "À-nouveaux générés", allocate: "Résultat affecté", cancel: "Affectation annulée",
  delete: "Écriture supprimée", provisional: "Clôture provisoire", final: "Clôture définitive", reopen: "Réouverture",
};
const DESCRIPTIONS: Record<string, string> = {
  checks: "Rapprochements, écritures déséquilibrées ou hors dates, factures d'achat non comptabilisées, comptes d'attente.",
  inventory: "Charges à payer, produits à recevoir, charges et produits constatés d'avance, datés du dernier jour de l'exercice.",
  dedicated_funds: "Subventions ou dons affectés non utilisés à la clôture (comptes 689 / 19).",
  result: "Produits (classe 7) moins charges (classe 6), écritures d'inventaire comprises.",
  fec: "Fichier des écritures comptables produit à blanc et relu avant la clôture.",
  close: "Clôture provisoire : écritures verrouillées et numérotées. Clôture définitive : FEC figé, irréversible.",
  opening: "À-nouveaux et extournes des écritures d'inventaire sur l'exercice suivant.",
  allocation: "Décision de l'assemblée générale sur l'affectation du résultat.",
};

export default function ClosingPage() {
  const id = Number(useParams().fy_id);
  const key = ["closing", id];
  const { data } = useQuery({ queryKey: key, queryFn: () => api.get<ClosingView>(`/api/v1/fiscal-years/${id}/closing`) });
  const [current, setCurrent] = useState<string | null>(null);
  if (!data) return <Center h={200}><Loader /></Center>;
  const fy = data.fiscal_year;
  // Première étape à faire (après la clôture : ouverture puis affectation), sinon l'étape Clôture.
  const active = data.steps.find((s) => s.key === current)
    ?? data.steps.find((s) => s.available && s.state === "todo"
      && (fy.status === "open" || ["opening", "allocation"].includes(s.key)))
    ?? data.steps.find((s) => s.key === "close")!;
  return (
    <>
      <PageHeader title={`Clôture de l'exercice ${fy.label}`}
        description={<>Exercice {fy.status_label.toLowerCase()} · <Anchor component={AppLink} href="/fiscal-years/" size="sm">Retour aux exercices</Anchor></>} />
      <Grid>
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Paper p="xs">
            {data.steps.map((s, i) => (
              <NavLink key={s.key} component="button" active={s.key === active.key} onClick={() => setCurrent(s.key)}
                label={`${i + 1}. ${s.label}`} disabled={!s.available}
                description={s.available ? s.note ?? undefined : "Après la clôture"}
                rightSection={s.available ? <StatusBadge tone={STATES[s.state][1]}>{STATES[s.state][0]}</StatusBadge> : null} />
            ))}
          </Paper>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Paper p="md">
            <Stack>
              <div>
                <Title order={2}>{active.label}</Title>
                <Text size="sm" c="dimmed">{DESCRIPTIONS[active.key]}</Text>
              </div>
              <StepBody step={active} view={data} />
              {!["close", "opening", "allocation"].includes(active.key) && active.available && <StepActions step={active} view={data} />}
            </Stack>
          </Paper>
          <History events={data.events} steps={data.steps} />
        </Grid.Col>
      </Grid>
    </>
  );
}

function useClosingAction<V>(fyId: number, request: (vars: V) => Promise<{ notices?: Notice[] }>) {
  return useAction(request, { invalidate: [["closing", fyId], FISCAL_YEARS_KEY, ["fec-preview", fyId], ["fec-check", fyId]] });
}

function StepBody({ step, view }: { step: Step; view: ClosingView }) {
  const fy = view.fiscal_year;
  switch (step.key) {
    case "checks": return <Checks checks={view.checks} />;
    case "inventory": return <Inventory view={view} />;
    case "dedicated_funds":
      return <Text size="sm">Le suivi des fonds dédiés arrive avec la phase A.6. Sans subvention ou don affecté restant à
        utiliser, ignorez l'étape en indiquant « sans objet ».</Text>;
    case "result": return <Result result={view.result} />;
    case "fec": return <FecPanel fiscalYearId={fy.id} preview={fy.status === "open"} />;
    case "close": return <Close view={view} />;
    case "opening": return <Opening view={view} />;
    case "allocation": return <Allocation view={view} />;
    default: return null;
  }
}

function StepActions({ step, view }: { step: Step; view: ClosingView }) {
  const can = useCan();
  const fyId = view.fiscal_year.id;
  const [note, setNote] = useState("");
  const [skipping, setSkipping] = useState(false);
  const save = useClosingAction(fyId, (body: { state: StepState; note?: string }) =>
    api.post(`/api/v1/fiscal-years/${fyId}/closing/${step.key}`, body));
  if (!can.write || view.fiscal_year.status !== "open") return null;
  const anomalies = step.key === "checks" && view.checks.some((c) => c.severity === "anomaly");
  if (skipping) {
    return (
      <Stack gap="xs">
        <Textarea label="Motif" description="Obligatoire pour ignorer une étape (5 caractères au moins)." autosize minRows={2}
          value={note} onChange={(e) => setNote(e.currentTarget.value)} data-autofocus />
        <Group>
          <Button loading={save.isPending} disabled={note.trim().length < 5}
            onClick={() => save.mutate({ state: "skipped", note }, { onSuccess: () => setSkipping(false) })}>Ignorer l'étape</Button>
          <Button variant="default" onClick={() => setSkipping(false)}>Annuler</Button>
        </Group>
      </Stack>
    );
  }
  return (
    <Group>
      {step.state !== "done" && (
        <Button loading={save.isPending} disabled={anomalies} title={anomalies ? "Traitez les anomalies ou ignorez l'étape avec un motif" : undefined}
          onClick={() => save.mutate({ state: "done" })}>Marquer comme fait</Button>
      )}
      {step.state !== "skipped" && <Button variant="default" onClick={() => { setNote(step.note ?? ""); setSkipping(true); }}>Ignorer…</Button>}
      {step.state !== "todo" && <Button variant="subtle" onClick={() => save.mutate({ state: "todo" })}>Remettre à faire</Button>}
    </Group>
  );
}

function Checks({ checks }: { checks: Check[] }) {
  if (!checks.length) return <Text size="sm" c="var(--lv-lichen)">✓ Aucune anomalie détectée.</Text>;
  return (
    <Table>
      <Table.Tbody>
        {checks.map((c) => (
          <Table.Tr key={c.key}>
            <Table.Td><StatusBadge tone={c.severity === "anomaly" ? "gap" : "info"}>{c.severity === "anomaly" ? "Anomalie" : "Info"}</StatusBadge></Table.Td>
            <Table.Td>{c.label}</Table.Td>
            <Table.Td className="lv-num" ta="right">{c.count}</Table.Td>
            <Table.Td ta="right">{c.url && <Anchor component={AppLink} href={c.url} size="sm">Voir</Anchor>}</Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}

function Inventory({ view }: { view: ClosingView }) {
  const can = useCan();
  const fyId = view.fiscal_year.id;
  const editable = can.write && view.fiscal_year.status === "open";
  const remove = useClosingAction(fyId, (entryId: number) => api.delete(`/api/v1/fiscal-years/${fyId}/inventory/${entryId}`));
  return (
    <Stack>
      {view.inventory.length ? (
        <Table>
          <Table.Thead><Table.Tr><Table.Th>Type</Table.Th><Table.Th>Libellé</Table.Th><Table.Th>Comptes</Table.Th>
            <Table.Th ta="right">Montant</Table.Th>{editable && <Table.Th />}</Table.Tr></Table.Thead>
          <Table.Tbody>
            {view.inventory.map((e) => (
              <Table.Tr key={e.id}>
                <Table.Td>{e.kind_label}</Table.Td>
                <Table.Td>{e.description}</Table.Td>
                <Table.Td className="lv-num">{e.lines.map((l) => l.account).join(" / ")}</Table.Td>
                <Table.Td ta="right"><MoneyText cents={e.amount_cents} /></Table.Td>
                {editable && <Table.Td ta="right">
                  <Button variant="subtle" size="compact-sm" color="brique" onClick={() => confirmAction({
                    title: `Supprimer l'écriture ${e.reference} ?`, confirmLabel: "Supprimer", onConfirm: () => remove.mutate(e.id),
                  })}>Supprimer</Button>
                </Table.Td>}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      ) : <Text size="sm" c="dimmed">Aucune écriture d'inventaire.</Text>}
      {editable && <InventoryForm view={view} />}
    </Stack>
  );
}

function InventoryForm({ view }: { view: ClosingView }) {
  const fyId = view.fiscal_year.id;
  const [kind, setKind] = useState("accrued_expense");
  const [account, setAccount] = useState<Account | null>(null);
  const [counterpart, setCounterpart] = useState<string | null>(null);
  const [amount, setAmount] = useState<number | null>(null);
  const [label, setLabel] = useState("");
  const option = view.inventory_options[kind];
  const add = useClosingAction(fyId, () => api.post<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fyId}/inventory`, {
    kind, account_code: account?.code, amount_cents: amount, label, counterpart_code: counterpart ?? undefined,
  }));
  return (
    <Paper withBorder p="sm">
      <Text fw={600} size="sm" mb="xs">Ajouter une écriture d'inventaire</Text>
      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        <Select label="Type" allowDeselect={false} value={kind}
          data={Object.entries(view.inventory_options).map(([value, o]) => ({ value, label: o.label }))}
          onChange={(v) => { setKind(v ?? "accrued_expense"); setAccount(null); setCounterpart(null); }} />
        <AccountSelect label={`Compte de classe ${option.classes.join("/")}`} recentsScope="inventory" value={account} onChange={setAccount} />
        <Select label="Contrepartie" placeholder={option.counterparts[0]?.label ?? "Créée au besoin"} clearable
          data={option.counterparts} value={counterpart} onChange={setCounterpart} />
        <MoneyInput label="Montant" value={amount} onChange={setAmount} />
      </SimpleGrid>
      <TextInput label="Libellé" mt="xs" value={label} onChange={(e) => setLabel(e.currentTarget.value)} />
      <Group mt="sm">
        <Button loading={add.isPending} disabled={!account || !amount} onClick={() => add.mutate(undefined, {
          onSuccess: () => { setAccount(null); setAmount(null); setLabel(""); },
        })}>Enregistrer l'écriture</Button>
      </Group>
    </Paper>
  );
}

function Result({ result }: { result: ClosingView["result"] }) {
  const surplus = result.result_cents >= 0;
  return (
    <SimpleGrid cols={{ base: 1, sm: 3 }}>
      <Figure label="Produits" value={<MoneyText cents={result.income_cents} />} />
      <Figure label="Charges" value={<MoneyText cents={result.expense_cents} />} />
      <Figure label={surplus ? "Excédent" : "Déficit"} value={<MoneyText cents={result.result_cents} anomaly={!surplus} />} />
    </SimpleGrid>
  );
}

function Close({ view }: { view: ClosingView }) {
  const can = useCan();
  const fy = view.fiscal_year;
  const [reopening, setReopening] = useState(false);
  const [reason, setReason] = useState("");
  const close = useClosingAction(fy.id, (final: boolean) => api.post(`/api/v1/fiscal-years/${fy.id}/close`, { final }));
  const reopen = useClosingAction(fy.id, () => api.post(`/api/v1/fiscal-years/${fy.id}/reopen`, { reason }));
  const pending = view.steps.filter((s) => s.available && s.key !== "close" && s.state === "todo"
    && !["opening", "allocation"].includes(s.key));
  return (
    <Stack>
      {fy.status === "open" && (pending.length ? (
        <Alert color="paille" title="Étapes à terminer avant la clôture">
          <List size="sm">{pending.map((s) => <List.Item key={s.key}>{s.label}</List.Item>)}</List>
        </Alert>
      ) : <Text size="sm">Toutes les étapes sont faites ou ignorées : l'exercice peut passer en clôture provisoire.</Text>)}
      {fy.status === "provisional" && <Text size="sm">Écritures verrouillées et numérotées. La clôture définitive fige le FEC
        (empreinte SHA-256) ; elle est irréversible.</Text>}
      {fy.status === "closed" && <Text size="sm">Exercice clôturé définitivement. Le FEC figé se télécharge depuis la liste des exercices.</Text>}
      <Group>
        {fy.status === "open" && can.write && (
          <Button disabled={pending.length > 0} loading={close.isPending} onClick={() => confirmAction({
            title: `Clôture provisoire de l'exercice ${fy.label} ?`, danger: false, confirmLabel: "Clôturer",
            message: "Les écritures sont verrouillées et numérotées. Un administrateur peut rouvrir l'exercice tant que la clôture n'est pas définitive.",
            onConfirm: () => close.mutate(false),
          })}>Clôture provisoire</Button>
        )}
        {fy.status === "provisional" && can.instanceAdmin && (
          <>
            <Button color="brique" loading={close.isPending} onClick={() => confirmAction({
              title: `Clôture définitive de l'exercice ${fy.label} ?`, confirmLabel: "Clôturer définitivement",
              message: "Le FEC est figé et l'exercice ne pourra plus être rouvert. Opération irréversible.",
              onConfirm: () => close.mutate(true),
            })}>Clôture définitive</Button>
            <Button variant="default" onClick={() => { setReason(""); setReopening(true); }}>Rouvrir…</Button>
          </>
        )}
      </Group>
      <FormModal opened={reopening} onClose={() => setReopening(false)} title={`Rouvrir l'exercice ${fy.label}`}>
        <Stack>
          <Textarea label="Motif" required autosize minRows={2} value={reason} data-autofocus
            description="Conservé dans l'historique. La numérotation est retirée puis recalculée à la prochaine clôture."
            onChange={(e) => setReason(e.currentTarget.value)} />
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setReopening(false)}>Annuler</Button>
            <Button loading={reopen.isPending} disabled={!reason.trim()}
              onClick={() => reopen.mutate(undefined, { onSuccess: () => setReopening(false) })}>Rouvrir l'exercice</Button>
          </Group>
        </Stack>
      </FormModal>
    </Stack>
  );
}

function Opening({ view }: { view: ClosingView }) {
  const can = useCan();
  const fy = view.fiscal_year;
  const { opening, allocation } = view;
  const next = view.next_fiscal_year;
  const generate = useClosingAction(fy.id, (createNext: boolean) =>
    api.post<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fy.id}/opening`, { create_next: createNext }));
  const allocated = !!allocation.decided_on;
  const nextYear = next?.label ?? opening.next_start_date.slice(0, 4);
  return (
    <Stack>
      {opening.error && <Alert color="brique" title="À-nouveaux impossibles">{opening.error}</Alert>}
      {opening.lines.length > 0 && (
        <Table>
          <Table.Thead><Table.Tr><Table.Th>Compte</Table.Th><Table.Th>Libellé</Table.Th>
            <Table.Th ta="right">Débit</Table.Th><Table.Th ta="right">Crédit</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {opening.lines.map((l) => (
              <Table.Tr key={l.account_code}>
                <Table.Td className="lv-num">{l.account_code}</Table.Td><Table.Td>{l.label}</Table.Td>
                <Table.Td ta="right">{l.debit_cents ? <MoneyText cents={l.debit_cents} /> : null}</Table.Td>
                <Table.Td ta="right">{l.credit_cents ? <MoneyText cents={l.credit_cents} /> : null}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
      <Text size="sm">
        À-nouveaux datés du {formatDate(opening.next_start_date)} (journal AN)
        {opening.reversals_planned > 0 && `, ${opening.reversals_planned} extourne(s) d'écritures d'inventaire`}.
      </Text>
      {opening.entries.length > 0 && (
        <Text size="sm">Déjà générées en {nextYear} :{" "}
          {opening.entries.map((e, i) => <span key={e.id}>{i > 0 && ", "}<Anchor component={AppLink} href={e.url} size="sm">{e.reference}</Anchor></span>)}
        </Text>
      )}
      {allocated && <Text size="sm" c="dimmed">Résultat affecté : annulez l'affectation (étape 8) pour regénérer les à-nouveaux.</Text>}
      {can.write && !allocated && !opening.error && (next ? next.status === "open" : true) && (
        <Group>
          <Button loading={generate.isPending} onClick={() => generate.mutate(!next)}>
            {!next ? `Créer l'exercice ${nextYear} et générer` : opening.entries.length ? "Regénérer les à-nouveaux" : "Générer les à-nouveaux"}
          </Button>
        </Group>
      )}
    </Stack>
  );
}

const BODIES = ["Assemblée générale", "Assemblée des associés", "Conseil d'administration"];

function Allocation({ view }: { view: ClosingView }) {
  const can = useCan();
  const fy = view.fiscal_year;
  const { allocation } = view;
  const amount = allocation.result_cents;
  const cancel = useClosingAction(fy.id, () => api.delete<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fy.id}/allocation`));
  const summary = amount === 0 ? "Résultat nul" : amount > 0 ? "Excédent à affecter" : "Déficit à affecter";
  return (
    <Stack>
      <Figure label={summary} value={<MoneyText cents={Math.abs(amount)} anomaly={amount < 0} />} />
      {allocation.decided_on ? (
        <>
          <Text size="sm">Décision : {allocation.body} du {formatDate(allocation.decided_on)}
            {allocation.entry && <> · écriture <Anchor component={AppLink} href={allocation.entry.url} size="sm">{allocation.entry.reference}</Anchor></>}.
          </Text>
          {can.write && <Group><Button variant="default" color="brique" loading={cancel.isPending} onClick={() => confirmAction({
            title: "Annuler l'affectation du résultat ?", confirmLabel: "Annuler l'affectation",
            message: "L'écriture d'affectation est supprimée ; la décision pourra être saisie de nouveau.",
            onConfirm: () => cancel.mutate(undefined),
          })}>Annuler l'affectation</Button></Group>}
        </>
      ) : can.write ? <AllocationForm view={view} /> : <Text size="sm" c="dimmed">Pas encore de décision d'affectation.</Text>}
    </Stack>
  );
}

function AllocationForm({ view }: { view: ClosingView }) {
  const fyId = view.fiscal_year.id;
  const { allocation, next_fiscal_year: next } = view;
  const target = Math.abs(allocation.result_cents);
  const [decidedOn, setDecidedOn] = useState<string | null>(null);
  const [body, setBody] = useState("Assemblée générale");
  const [lines, setLines] = useState<{ account: string | null; amount: number | null }[]>(
    [{ account: null, amount: target || null }]);
  const total = lines.reduce((sum, l) => sum + (l.amount ?? 0), 0);
  const save = useClosingAction(fyId, () => api.post<{ notices: Notice[] }>(`/api/v1/fiscal-years/${fyId}/allocation`, {
    decided_on: decidedOn, body,
    lines: target ? lines.map((l) => ({ account_code: l.account, amount_cents: l.amount })) : [],
  }));
  const update = (i: number, patch: Partial<(typeof lines)[number]>) =>
    setLines(lines.map((l, j) => (j === i ? { ...l, ...patch } : l)));
  return (
    <Paper withBorder p="sm">
      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        <DateInput label="Date de la décision" required valueFormat="DD/MM/YYYY" value={decidedOn} onChange={setDecidedOn}
          minDate={next?.start_date} maxDate={next?.end_date} />
        <Autocomplete label="Organe" required data={BODIES} value={body} onChange={setBody} />
      </SimpleGrid>
      {target > 0 && (
        <Stack gap="xs" mt="sm">
          {lines.map((l, i) => (
            <Group key={i} align="flex-end" wrap="nowrap">
              <Select label={i === 0 ? "Compte" : undefined} aria-label="Compte" placeholder="10x, 11x ou 455x" searchable
                data={allocation.options} value={l.account} onChange={(v) => update(i, { account: v })} style={{ flex: 2 }} />
              <MoneyInput label={i === 0 ? "Montant" : undefined} aria-label="Montant" value={l.amount}
                onChange={(v) => update(i, { amount: v })} style={{ flex: 1 }} />
              {lines.length > 1 && <ActionIcon variant="subtle" color="brique" aria-label="Retirer la ligne" mb={6}
                onClick={() => setLines(lines.filter((_l, j) => j !== i))}>×</ActionIcon>}
            </Group>
          ))}
          <Group justify="space-between">
            <Button variant="subtle" size="compact-sm" onClick={() => setLines([...lines, { account: null, amount: target - total > 0 ? target - total : null }])}>
              Ajouter une ligne
            </Button>
            <Text size="sm" c={total === target ? undefined : "var(--lv-brique)"}>
              Réparti : <MoneyText cents={total} /> / <MoneyText cents={target} />
            </Text>
          </Group>
        </Stack>
      )}
      <Group mt="sm">
        <Button loading={save.isPending} disabled={!decidedOn || !body.trim() || (target > 0 && (total !== target || lines.some((l) => !l.account)))}
          onClick={() => save.mutate(undefined)}>Enregistrer l'affectation</Button>
      </Group>
    </Paper>
  );
}

function History({ events, steps }: { events: ClosingEvent[]; steps: Step[] }) {
  if (!events.length) return null;
  const labels = Object.fromEntries(steps.map((s) => [s.key, s.label]));
  return (
    <Paper p="md" mt="md">
      <Title order={3} mb="xs">Historique</Title>
      <Table>
        <Table.Tbody>
          {events.map((e, i) => (
            <Table.Tr key={i}>
              <Table.Td className="lv-num" w={150}>{formatDateTime(e.at)}</Table.Td>
              <Table.Td>{ACTIONS[e.action] ?? e.action}{e.step && e.step !== "close" ? ` — ${labels[e.step] ?? e.step}` : ""}</Table.Td>
              <Table.Td><Text size="sm" c="dimmed">{describe(e.details)}</Text></Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Paper>
  );
}

function describe(details: Record<string, unknown> | null) {
  if (!details) return "";
  return [details.note, details.reason, details.body, details.entry].filter(Boolean).join(" · ");
}

function Figure({ label, value }: { label: string; value: React.ReactNode }) {
  return <div><Text size="xs" c="dimmed">{label}</Text><Text fw={600} size="lg" className="lv-num">{value}</Text></div>;
}
