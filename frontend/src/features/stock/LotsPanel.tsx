// Inventaire de clôture › Animaux (lot AG4.b, claudedocs/design_inventaire_agricole.md § 5.5) : lots d'animaux en
// stock, mouvements en têtes (naissance, achat, vente, mort, passage dans un autre lot, sortie vers les
// immobilisations), effectif théorique comparé à l'effectif compté. Aucune écriture.
import { useState } from "react";
import { Alert, Button, Drawer, Group, Loader, NumberInput, Paper, Select, Stack, Table, Text, TextInput } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { formatDate } from "../../lib/format";
import { MoneyInput } from "../../components/Money";

export interface LotSummary {
  opening: number; opening_source: "previous" | "movement"; movements: Record<string, number>; entries: number; exits: number;
  theoretical: number; counted: number | null; gap: number | null; line_id: number | null;
}
export interface StockLotItem {
  id: number; label: string; species: string; age_class: string | null; destination: string; destination_label: string;
  account: { id: number; code: string; label: string }; average_weight_kg: string | null; active: boolean; summary?: LotSummary;
  movements?: { id: number; on: string; kind: string; kind_label: string; heads: number; sign: number; note: string | null;
    counterpart: { id: number; label: string } | null; paired: boolean; asset?: { id: number; label: string } | null }[];
}

const KINDS = [{ value: "opening", label: "Effectif d'ouverture" }, { value: "birth", label: "Naissance" },
  { value: "purchase", label: "Achat" }, { value: "sale", label: "Vente" }, { value: "death", label: "Mort" },
  { value: "transfer_out", label: "Passage dans un autre lot" }, { value: "to_fixed_assets", label: "Sortie vers les immobilisations" }];
const DESTINATIONS = [{ value: "sale", label: "Vente" }, { value: "fattening", label: "Engraissement" },
  { value: "breeding", label: "Renouvellement" }, { value: "other", label: "Autre" }];
const errorOf = (e: unknown) => (e instanceof ApiError ? e.message : "Enregistrement impossible.");

function LotDrawer({ lotId, fyId, lots, editable, invalidate, onClose }: {
  lotId: number | null; fyId: number; lots: StockLotItem[]; editable: boolean; invalidate: unknown[][]; onClose: () => void;
}) {
  const key = ["stock-lots", lotId, fyId];
  const { data } = useQuery({ queryKey: key, enabled: lotId !== null,
    queryFn: () => api.get<{ item: StockLotItem }>(`/api/v1/stock-lots/${lotId}?fiscal_year_id=${fyId}`) });
  const [m, setM] = useState<{ on: string | null; kind: string; heads: number | ""; counterpart: string | null; note: string }>(
    { on: null, kind: "birth", heads: "", counterpart: null, note: "" });
  const [error, setError] = useState<string | null>(null);
  const opts = { invalidate: [...invalidate, ["stock-lots"]] };
  const add = useAction((body: object) => api.post<{ notices: Notice[] }>(`/api/v1/stock-lots/${lotId}/movements?fiscal_year_id=${fyId}`, body), opts);
  const toAssets = useAction((body: object) => api.post<{ notices: Notice[] }>(`/api/v1/stock-lots/${lotId}/to-fixed-assets`, body),
    { invalidate: [...opts.invalidate, ["assets"]] });
  const { data: herds } = useQuery({ queryKey: ["assets", "living-herds"], enabled: m.kind === "to_fixed_assets",
    queryFn: () => api.get<{ items: { id: number; label: string; status: string; account: { code: string } }[] }>("/api/v1/assets?living=1") });
  const [fa, setFa] = useState<{ value: number | null; account: string; parent: string | null; duration: number | "" }>(
    { value: null, account: "241", parent: null, duration: "" });
  const remove = useAction((id: number) => api.delete<{ notices: Notice[] }>(`/api/v1/stock-lots/${lotId}/movements/${id}?fiscal_year_id=${fyId}`), opts);
  const lot = data?.item;
  return (
    <Drawer opened={lotId !== null} onClose={onClose} position="right" size="lg" title={lot ? `${lot.label} (${lot.account.code})` : ""}>
      {!lot?.summary ? <Loader /> : (
        <Stack>
          <Text size="sm">Ouverture {lot.summary.opening} ({lot.summary.opening_source === "previous" ? "inventaire précédent" : "saisie"})
            · entrées {lot.summary.entries} · sorties {lot.summary.exits} · <b>théorique {lot.summary.theoretical}</b>
            {lot.summary.counted !== null && ` · compté ${lot.summary.counted}`}</Text>
          <Table>
            <Table.Tbody>
              {(lot.movements ?? []).map((mv) => (
                <Table.Tr key={mv.id}>
                  <Table.Td>{formatDate(mv.on)}</Table.Td>
                  <Table.Td>{mv.kind_label}{mv.counterpart && ` (${mv.counterpart.label})`}{mv.note && <Text size="xs" c="dimmed">{mv.note}</Text>}
                    {mv.asset && <Text size="xs" c="dimmed">fiche « {mv.asset.label} » (D 24x / C 724)</Text>}</Table.Td>
                  <Table.Td ta="right" className="lv-num">{mv.sign > 0 ? "+" : "−"}{mv.heads}</Table.Td>
                  <Table.Td>{editable && <Button size="compact-xs" variant="subtle" color="brique" onClick={() => remove.mutate(mv.id)}>Supprimer</Button>}</Table.Td>
                </Table.Tr>))}
            </Table.Tbody>
          </Table>
          {editable && (
            <form onSubmit={(e) => {
              e.preventDefault(); setError(null);
              const request = m.kind === "to_fixed_assets"
                ? toAssets.mutateAsync({ on: m.on, heads: m.heads === "" ? null : m.heads, note: m.note || undefined, value_cents: fa.value,
                  account_code: fa.parent ? undefined : fa.account, parent_id: fa.parent ? Number(fa.parent) : undefined,
                  duration_months: fa.duration === "" ? undefined : fa.duration })
                : add.mutateAsync({ on: m.on, kind: m.kind, heads: m.heads === "" ? null : m.heads, note: m.note || undefined,
                  counterpart_lot_id: m.kind === "transfer_out" && m.counterpart ? Number(m.counterpart) : undefined });
              request.then(() => setM({ ...m, heads: "", note: "" }), (er) => setError(errorOf(er)));
            }}>
              <Group align="end" gap="xs">
                <DateInput label="Date" required valueFormat="DD/MM/YYYY" w={130} value={m.on} onChange={(v) => setM({ ...m, on: v })} />
                <Select label="Mouvement" w={210} data={KINDS} value={m.kind} allowDeselect={false} onChange={(v) => setM({ ...m, kind: v ?? "birth" })} />
                <NumberInput label="Têtes" w={90} min={1} value={m.heads} onChange={(v) => setM({ ...m, heads: typeof v === "number" ? v : "" })} />
                {m.kind === "transfer_out" && <Select label="Vers le lot" w={200} value={m.counterpart}
                  data={lots.filter((l) => l.id !== lotId).map((l) => ({ value: String(l.id), label: l.label }))} onChange={(v) => setM({ ...m, counterpart: v })} />}
                {m.kind === "to_fixed_assets" && (
                  <>
                    <MoneyInput label="Valeur d'entrée" w={130} value={fa.value} onChange={(v) => setFa({ ...fa, value: v })} />
                    <Select label="Lot immobilisé" w={200} clearable placeholder="nouvelle fiche" value={fa.parent}
                      data={(herds?.items ?? []).filter((h) => h.status === "in_use" || h.status === "depreciated").map((h) => ({ value: String(h.id), label: h.label }))}
                      onChange={(v) => setFa({ ...fa, parent: v })} />
                    {!fa.parent && <Select label="Compte" w={150} value={fa.account} allowDeselect={false} onChange={(v) => setFa({ ...fa, account: v ?? "241" })}
                      data={[{ value: "241", label: "241 reproducteurs" }, { value: "243", label: "243 service" }]} />}
                    {!fa.parent && <NumberInput label="Durée (mois)" w={100} min={1} value={fa.duration} onChange={(v) => setFa({ ...fa, duration: typeof v === "number" ? v : "" })} />}
                  </>)}
                <TextInput label="Note" w={160} value={m.note} onChange={(e) => setM({ ...m, note: e.currentTarget.value })} />
                <Button type="submit" variant="light" loading={add.isPending || toAssets.isPending}>Ajouter</Button>
              </Group>
              {error && <Alert color="brique" mt="xs">{error}</Alert>}
            </form>)}
        </Stack>)}
    </Drawer>
  );
}

export function LotsPanel({ fyId, lots, editable, invalidate }: { fyId: number; lots: StockLotItem[]; editable: boolean; invalidate: unknown[][] }) {
  const [open, setOpen] = useState<number | null>(null);
  const [draft, setDraft] = useState<{ species: string; age_class: string; account_code: string; destination: string; weight: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const create = useAction((body: object) => api.post<{ notices: Notice[] }>(`/api/v1/stock-lots?fiscal_year_id=${fyId}`, body), { invalidate });
  return (
    <Paper withBorder p="sm" mb="lg">
      <Group justify="space-between" mb={4}>
        <Text fw={600} size="sm">Lots d'animaux</Text>
        {editable && !draft && <Button size="xs" variant="light" onClick={() => setDraft({ species: "", age_class: "", account_code: "3113", destination: "sale", weight: "" })}>Nouveau lot</Button>}
      </Group>
      <Text size="xs" c="dimmed" mb="xs">Même espèce, même catégorie d'âge, même destination. Effectif théorique = ouverture + entrées − sorties ;
        l'effectif compté se saisit sur la ligne d'inventaire du lot.</Text>
      {lots.length === 0 ? <Text size="sm" c="dimmed">Aucun lot.</Text> : (
        <Table highlightOnHover>
          <Table.Thead><Table.Tr><Table.Th>Lot</Table.Th><Table.Th>Compte</Table.Th><Table.Th ta="right">Ouverture</Table.Th>
            <Table.Th ta="right">Entrées</Table.Th><Table.Th ta="right">Sorties</Table.Th><Table.Th ta="right">Théorique</Table.Th>
            <Table.Th ta="right">Compté</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {lots.map((l) => (
              <Table.Tr key={l.id} style={{ cursor: "pointer" }} onClick={() => setOpen(l.id)}>
                <Table.Td>{l.label}<Text size="xs" c="dimmed">{l.destination_label}</Text></Table.Td>
                <Table.Td className="lv-num">{l.account.code}</Table.Td>
                <Table.Td ta="right">{l.summary?.opening}</Table.Td><Table.Td ta="right">{l.summary?.entries}</Table.Td>
                <Table.Td ta="right">{l.summary?.exits}</Table.Td><Table.Td ta="right"><b>{l.summary?.theoretical}</b></Table.Td>
                <Table.Td ta="right">{l.summary?.counted ?? "—"}
                  {l.summary?.gap ? <Text span size="xs" c="var(--lv-paille-ink)"> ({l.summary.gap > 0 ? "+" : ""}{l.summary.gap})</Text> : null}</Table.Td>
              </Table.Tr>))}
          </Table.Tbody>
        </Table>)}
      {draft && (
        <Group align="end" gap="xs" mt="xs">
          <TextInput label="Espèce" required w={140} value={draft.species} onChange={(e) => setDraft({ ...draft, species: e.currentTarget.value })} />
          <TextInput label="Catégorie d'âge" w={160} value={draft.age_class} onChange={(e) => setDraft({ ...draft, age_class: e.currentTarget.value })} />
          <Select label="Compte" w={170} value={draft.account_code} allowDeselect={false} onChange={(v) => setDraft({ ...draft, account_code: v ?? "3113" })}
            data={[{ value: "3113", label: "3113 cycle court" }, { value: "3112", label: "3112 cycle long" }]} />
          <Select label="Destination" w={150} data={DESTINATIONS} value={draft.destination} allowDeselect={false} onChange={(v) => setDraft({ ...draft, destination: v ?? "sale" })} />
          <TextInput label="Poids moyen (kg)" w={120} value={draft.weight} onChange={(e) => setDraft({ ...draft, weight: e.currentTarget.value })} />
          <Button disabled={!draft.species} loading={create.isPending} onClick={() => {
            setError(null);
            create.mutateAsync({ species: draft.species, age_class: draft.age_class || undefined, account_code: draft.account_code,
              destination: draft.destination, average_weight_kg: draft.weight || undefined }).then(() => setDraft(null), (e) => setError(errorOf(e)));
          }}>Créer</Button>
          <Button variant="default" onClick={() => setDraft(null)}>Annuler</Button>
        </Group>)}
      {error && <Alert color="brique" mt="xs">{error}</Alert>}
      <LotDrawer lotId={open} fyId={fyId} lots={lots} editable={editable} invalidate={invalidate} onClose={() => setOpen(null)} />
    </Paper>
  );
}
