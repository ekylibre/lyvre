// Inventaire › Quantités depuis Ekylibre (lot AG11.d) : matières lues dans Ekylibre (par variante), rattachées à une
// ligne d'inventaire (ou en créant une) ; quantités reportées si la lecture est à 7 jours au plus de la date
// d'inventaire. La valeur reste celle de la méthode de la ligne.
import { useState } from "react";
import { Alert, Button, Checkbox, Group, Select, Stack, Table, Text, TextInput } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { formatDate, formatDateTime } from "../../lib/format";

export interface EkylibreInventoryData {
  fiscal_year: { id: number; label: string; open: boolean }; inventory_date: string; synced_at: string | null;
  gap_days: number | null; allowed: boolean; max_gap_days: number;
  items: { variant_id: number; name: string; matters: number; quantity: string; unit: string | null; raw_unit: string | null;
    mixed_units: boolean; line: { id: number; label: string; account: string; quantity: string; unit: string } | null;
    link: { account: string; label: string } | null; converted: string | null }[];
  lines: { value: string; label: string; unit: string }[];
}

type Choice = { checked: boolean; target: string; account: string };   // target : id de ligne, ou "new"

export function EkylibreInventoryView({ data, onApply, pending }: {
  data: EkylibreInventoryData; onApply: (items: object[]) => void; pending?: boolean;
}) {
  const [choices, setChoices] = useState<Record<number, Choice>>(() => Object.fromEntries(data.items.map((i) =>
    [i.variant_id, { checked: !!i.line, target: i.line ? String(i.line.id) : "", account: "" }])));
  const set = (id: number, patch: Partial<Choice>) => setChoices((c) => ({ ...c, [id]: { ...c[id], ...patch } }));
  const chosen = data.items.filter((i) => choices[i.variant_id]?.checked && choices[i.variant_id].target
    && (choices[i.variant_id].target !== "new" || choices[i.variant_id].account));
  const apply = () => onApply(chosen.map((i) => {
    const c = choices[i.variant_id];
    return c.target === "new" ? { variant_id: i.variant_id, create: { account_code: c.account, label: i.name } }
      : { variant_id: i.variant_id, line_id: Number(c.target) };
  }));
  return (
    <Stack>
      <Text size="sm">Date d'inventaire : {formatDate(data.inventory_date)}.{" "}
        {data.synced_at ? `Dernière lecture d'Ekylibre : ${formatDateTime(data.synced_at)}.` : "Ekylibre n'a pas encore été lu."}</Text>
      {!data.allowed && <Alert color="paille">
        {data.synced_at ? `Lecture à ${data.gap_days} jours de la date d'inventaire : lisez Ekylibre à ${data.max_gap_days} jours au plus pour reporter les quantités.`
          : "Lisez d'abord Ekylibre (Intégrations › Ekylibre)."}</Alert>}
      <Table>
        <Table.Thead><Table.Tr><Table.Th /><Table.Th>Matière Ekylibre</Table.Th><Table.Th ta="right">Quantité</Table.Th>
          <Table.Th>Ligne d'inventaire</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>
          {data.items.map((i) => {
            const c = choices[i.variant_id];
            return (
              <Table.Tr key={i.variant_id}>
                <Table.Td><Checkbox aria-label={`Reporter ${i.name}`} checked={c?.checked ?? false}
                  onChange={(e) => set(i.variant_id, { checked: e.currentTarget.checked })} /></Table.Td>
                <Table.Td>{i.name}<Text size="xs" c="dimmed">{i.matters} lot(s)</Text></Table.Td>
                <Table.Td ta="right" className="lv-num">{i.quantity.replace(".", ",")} {i.raw_unit}
                  {(!i.unit || i.mixed_units) && <Text size="xs" c="var(--lv-brique)">unité non reconnue</Text>}
                  {i.line && i.converted && <Text size="xs" c="dimmed">soit {i.converted.replace(".", ",")} {i.line.unit}</Text>}</Table.Td>
                <Table.Td miw={260}>
                  <Select size="xs" aria-label={`Ligne pour ${i.name}`} placeholder="Choisir une ligne"
                    data={[{ value: "new", label: "Créer une ligne" }, ...data.lines]} value={c?.target || null}
                    onChange={(v) => set(i.variant_id, { target: v ?? "", checked: true })} />
                  {c?.target === "new" && <TextInput size="xs" mt={4} placeholder="Compte de stock (31…, 32…)" aria-label={`Compte pour ${i.name}`}
                    value={c.account} onChange={(e) => set(i.variant_id, { account: e.currentTarget.value })} />}
                  {i.line && <Text size="xs" c="dimmed">actuellement {i.line.quantity.replace(".", ",")} {i.line.unit}</Text>}
                  {i.link && <Text size="xs" c="dimmed">correspondance : {i.link.account} {i.link.label} (absente de l'exercice)</Text>}
                </Table.Td>
              </Table.Tr>
            );
          })}
        </Table.Tbody>
      </Table>
      <Group justify="flex-end">
        <Button disabled={!data.allowed || !data.fiscal_year.open || !chosen.length} loading={pending} onClick={apply}>
          Reporter les quantités ({chosen.length})</Button>
      </Group>
    </Stack>
  );
}

export function EkylibreInventory({ fiscalYearId, onDone }: { fiscalYearId: number; onDone: () => void }) {
  const key = ["ekylibre", "inventory", fiscalYearId];
  const { data, refetch } = useQuery({ queryKey: key,
    queryFn: () => api.get<EkylibreInventoryData>(`/api/v1/ekylibre/inventory?fiscal_year_id=${fiscalYearId}`) });
  const save = useAction((items: object[]) => api.post<{ notices: Notice[] }>("/api/v1/ekylibre/inventory",
    { fiscal_year_id: fiscalYearId, items }));
  if (!data) return null;
  if (!data.items.length) return <Text c="dimmed">Aucune matière avec quantité dans la dernière lecture d'Ekylibre.</Text>;
  return <EkylibreInventoryView key={data.synced_at ?? ""} data={data} pending={save.isPending}
    onApply={(items) => save.mutate(items, { onSuccess: () => { void refetch(); onDone(); } })} />;
}
