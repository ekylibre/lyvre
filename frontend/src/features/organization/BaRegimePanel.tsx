// Structure › Fiscalité › Régime BA (lot AG6.e, claudedocs/design_fiscalite_ba.md § 7) : moyenne triennale des
// recettes et régime de plein droit de l'exercice suivant (art. 69, 71), simulation micro ou réel, revenus accessoires
// (art. 75) avec repérage des comptes de produits, saisie des années antérieures à Lyvre.
import { useState } from "react";
import { Alert, Badge, Button, Fieldset, Group, Select, SimpleGrid, Stack, Table, Text, TextInput } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { MoneyInput, MoneyText } from "../../components/Money";
import { formatDate } from "../../lib/format";

type Option = { value: string; label: string };
type YearRow = { year: number; threshold_cents: number | null; agricultural_ttc_cents: number | null; accessory_ttc_cents: number | null; source: string };
type HistoryRow = { year: number; agricultural_receipts_cents: number | null; accessory_receipts_cents: number | null; fiscal_result_cents: number | null; note: string | null };
export interface BaRegimeView {
  fiscal_year: { id: number; label: string; end_date: string };
  regime: { years: YearRow[]; average_cents: number | null; thresholds: { micro_cents: number | null; normal_cents: number | null; detail: string | null };
    current: string | null; current_label: string | null; expected: string | null; expected_label: string | null; next_start: string;
    micro_allowed: boolean; micro_reason: string | null; change: { direction: string; label: string } | null; warnings: string[] };
  simulation: { micro_allowed: boolean; micro_reason: string | null; average_cents: number | null; micro_profit_cents: number | null;
    real_result_cents: number; real_basis: string; best: string | null; deadline: string; notes: string[] };
  accessory: { applicable: boolean; reason?: string; span?: number[]; young?: boolean; agricultural_avg_cents?: number | null; accessory_avg_cents?: number | null;
    limit_ratio_cents?: number; limit_cap_cents?: number; multiplier?: number; exceeded?: boolean; consequence?: string | null;
    current_share_bp?: number; accounts?: { id: number; code: string; label: string; class: string | null }[] };
  history: HistoryRow[]; classes: Option[];
}

const SOURCE: Record<string, string> = { lyvre: "Lyvre", entered: "saisie", missing: "inconnue" };

export function BaRegimePanel({ editable }: { editable: boolean }) {
  const { data: years } = useQuery({ queryKey: ["fiscal-years"],
    queryFn: () => api.get<{ items: { id: number; label: string; status: string }[] }>("/api/v1/fiscal-years") });
  const [fyChoice, setFyChoice] = useState<string | null>(null);
  const fyId = Number(fyChoice) || years?.items.find((y) => y.status === "open")?.id || years?.items[0]?.id;
  const { data, error } = useQuery({ queryKey: ["ba-regime", fyId], enabled: !!fyId,
    queryFn: () => api.get<{ item: BaRegimeView }>(`/api/v1/fiscal-years/${fyId}/ba-regime`) });
  const [draft, setDraft] = useState<{ year: string; agri: number | null; acc: number | null; result: number | null; note: string }>(
    { year: "", agri: null, acc: null, result: null, note: "" });
  const [failure, setFailure] = useState<string | null>(null);
  const opts = { invalidate: [["ba-regime"], ["tax-result"]] };
  const saveYear = useAction((b: { year: number; [key: string]: unknown }) => api.put<{ notices: Notice[] }>(`/api/v1/ba-history/${b.year}`, b), opts);
  const tag = useAction((v: { id: number; value: string | null }) => api.put<{ notices: Notice[] }>(`/api/v1/accounts/${v.id}/ba-income-class`, { ba_income_class: v.value }), opts);
  if (error || !years || !data || !fyId) return null;
  const { regime: r, simulation: s, accessory: a } = data.item;
  const run = (p: Promise<unknown>, after?: () => void) => { setFailure(null); p.then(after, (e) => setFailure(e instanceof ApiError ? e.message : "Enregistrement impossible.")); };
  return (
    <Fieldset legend="Régime des bénéfices agricoles">
      <Stack>
        <Select aria-label="Exercice" w={200} allowDeselect={false} value={String(fyId)} onChange={setFyChoice}
          data={years.items.map((y) => ({ value: String(y.id), label: `Exercice ${y.label}` }))} />
        {r.warnings.map((w) => <Alert key={w} color="paille">{w}</Alert>)}
        {r.change && <Alert color={r.change.direction === "up" ? "brique" : "gray"}>{r.change.label}</Alert>}
        <Table>
          <Table.Thead><Table.Tr><Table.Th>Année</Table.Th><Table.Th ta="right">Recettes (seuils, façon × 3)</Table.Th><Table.Th>Origine</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {r.years.map((y) => (
              <Table.Tr key={y.year}><Table.Td>{y.year}</Table.Td>
                <Table.Td ta="right">{y.threshold_cents !== null ? <MoneyText cents={y.threshold_cents} /> : "—"}</Table.Td>
                <Table.Td><Text size="xs" c="dimmed">{SOURCE[y.source] ?? y.source}</Text></Table.Td></Table.Tr>))}
          </Table.Tbody>
        </Table>
        <Text size="sm">
          Moyenne {r.average_cents !== null ? <MoneyText cents={r.average_cents} fw={600} /> : "inconnue"} ; seuils : micro-BA{" "}
          {r.thresholds.micro_cents !== null ? <MoneyText cents={r.thresholds.micro_cents} /> : "—"}, réel normal{" "}
          {r.thresholds.normal_cents !== null ? <MoneyText cents={r.thresholds.normal_cents} /> : "—"}{r.thresholds.detail ? ` (${r.thresholds.detail})` : ""}.
        </Text>
        <Group gap="xs">
          <Text size="sm">Régime en cours : <b>{r.current_label ?? "non renseigné"}</b></Text>
          {r.expected_label && <Badge color={r.change?.direction === "up" ? "brique" : "mousse"} variant="light">
            au {formatDate(r.next_start)} : {r.expected_label}</Badge>}
          {!r.micro_allowed && r.micro_reason && <Text size="xs" c="dimmed">Micro-BA impossible : {r.micro_reason}</Text>}
        </Group>

        <Text fw={600} size="sm" mt="sm">Simulation micro-BA ou réel ({data.item.fiscal_year.label})</Text>
        <SimpleGrid cols={{ base: 1, sm: 3 }}>
          <div><Text size="xs" c="dimmed">Bénéfice forfaitaire micro-BA</Text>
            {s.micro_allowed && s.micro_profit_cents !== null ? <MoneyText cents={s.micro_profit_cents} /> : <Text size="sm">{s.micro_reason ?? "recettes inconnues"}</Text>}</div>
          <div><Text size="xs" c="dimmed">Réel : {s.real_basis}</Text><MoneyText cents={s.real_result_cents} /></div>
          <div><Text size="xs" c="dimmed">Base imposable la plus faible</Text>
            <Text size="sm" fw={600}>{s.best === "micro" ? "Micro-BA" : s.best === "real" ? "Réel" : "—"}</Text></div>
        </SimpleGrid>
        <Text size="xs" c="dimmed">{s.deadline} {s.notes.join(" ")}</Text>

        <Text fw={600} size="sm" mt="sm">Revenus accessoires BIC / BNC (art. 75)</Text>
        {!a.applicable ? <Text size="sm">{a.reason}</Text> : (
          <>
            {a.exceeded && <Alert color="brique">{a.consequence === "is"
              ? "Limites dépassées : la société civile devient passible de l'IS de plein droit (art. 206-2). À examiner avec l'expert-comptable."
              : "Limites dépassées : les revenus accessoires s'imposent en BIC / BNC, hors bénéfice agricole."}</Alert>}
            <Text size="sm">
              Moyenne TTC {a.young ? `de ${a.span?.[0]} (premières années)` : `${a.span?.[0]}–${a.span?.[a.span.length - 1]}`} :
              accessoires {a.accessory_avg_cents != null ? <MoneyText cents={a.accessory_avg_cents} /> : "inconnus"}, recettes agricoles{" "}
              {a.agricultural_avg_cents != null ? <MoneyText cents={a.agricultural_avg_cents} /> : "inconnues"} ; limites{" "}
              <MoneyText cents={a.limit_ratio_cents ?? 0} /> (50 % des recettes agricoles) et <MoneyText cents={a.limit_cap_cents ?? 0} />
              {a.multiplier && a.multiplier > 1 ? ` (× ${a.multiplier} associés)` : ""}.
              {a.current_share_bp ? ` Part accessoire des produits de l'exercice : ${(a.current_share_bp / 100).toLocaleString("fr-FR")} % (ventilation BA / BIC estimée).` : ""}
            </Text>
            <Table>
              <Table.Thead><Table.Tr><Table.Th>Compte de produits</Table.Th><Table.Th>Repérage</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>
                {(a.accounts ?? []).filter((x) => editable || x.class).map((x) => (
                  <Table.Tr key={x.id}><Table.Td><Text size="sm">{x.code} {x.label}</Text></Table.Td>
                    <Table.Td>{editable ? (
                      <Select aria-label={`Repérage ${x.code}`} size="xs" w={300} clearable placeholder="recette agricole" data={data.item.classes}
                        value={x.class} onChange={(v) => run(tag.mutateAsync({ id: x.id, value: v }))} />
                    ) : data.item.classes.find((c) => c.value === x.class)?.label}</Table.Td></Table.Tr>))}
              </Table.Tbody>
            </Table>
          </>)}

        <Text fw={600} size="sm" mt="sm">Années antérieures à Lyvre</Text>
        <Text size="xs" c="dimmed">Recettes retenues pour les seuils (HT, façon × 3), recettes accessoires (TTC) et bénéfice agricole de
          l'exercice clos dans l'année ; une saisie l'emporte sur les écritures de Lyvre.</Text>
        {data.item.history.length > 0 && (
          <Table>
            <Table.Thead><Table.Tr><Table.Th>Année</Table.Th><Table.Th ta="right">Recettes</Table.Th><Table.Th ta="right">Accessoires</Table.Th>
              <Table.Th ta="right">Bénéfice</Table.Th><Table.Th>Note</Table.Th><Table.Th /></Table.Tr></Table.Thead>
            <Table.Tbody>
              {data.item.history.map((h) => (
                <Table.Tr key={h.year}><Table.Td>{h.year}</Table.Td>
                  <Table.Td ta="right">{h.agricultural_receipts_cents !== null ? <MoneyText cents={h.agricultural_receipts_cents} /> : "—"}</Table.Td>
                  <Table.Td ta="right">{h.accessory_receipts_cents !== null ? <MoneyText cents={h.accessory_receipts_cents} /> : "—"}</Table.Td>
                  <Table.Td ta="right">{h.fiscal_result_cents !== null ? <MoneyText cents={h.fiscal_result_cents} /> : "—"}</Table.Td>
                  <Table.Td><Text size="xs">{h.note}</Text></Table.Td>
                  <Table.Td>{editable && <Button size="compact-xs" variant="subtle" color="brique"
                    onClick={() => run(saveYear.mutateAsync({ year: h.year }))}>Retirer</Button>}</Table.Td></Table.Tr>))}
            </Table.Tbody>
          </Table>)}
        {editable && (
          <Group align="end" gap="xs">
            <TextInput label="Année" w={90} inputMode="numeric" value={draft.year} onChange={(e) => setDraft({ ...draft, year: e.currentTarget.value })} />
            <MoneyInput label="Recettes" w={140} value={draft.agri} onChange={(v) => setDraft({ ...draft, agri: v })} />
            <MoneyInput label="Accessoires (TTC)" w={140} value={draft.acc} onChange={(v) => setDraft({ ...draft, acc: v })} />
            <MoneyInput label="Bénéfice agricole" w={140} value={draft.result} onChange={(v) => setDraft({ ...draft, result: v })} />
            <TextInput label="Note" w={180} value={draft.note} onChange={(e) => setDraft({ ...draft, note: e.currentTarget.value })} />
            <Button variant="light" disabled={!/^\d{4}$/.test(draft.year)} onClick={() => run(saveYear.mutateAsync({
              year: Number(draft.year), agricultural_receipts_cents: draft.agri, accessory_receipts_cents: draft.acc,
              fiscal_result_cents: draft.result, note: draft.note }), () => setDraft({ year: "", agri: null, acc: null, result: null, note: "" }))}>Enregistrer</Button>
          </Group>)}
        {failure && <Alert color="brique">{failure}</Alert>}
      </Stack>
    </Fieldset>
  );
}
