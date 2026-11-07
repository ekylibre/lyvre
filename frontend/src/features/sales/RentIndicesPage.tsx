// Ventes › Indices de loyer (lot L5) : ILC, ILAT et IRL lus à l'INSEE, indice national des fermages
// saisi (arrêté annuel) ; une valeur saisie corrige celle de l'INSEE. Les révisions de loyer en
// attente d'un indice s'appliquent dès qu'il est connu.
import { useState } from "react";
import { ActionIcon, Button, Group, Paper, SegmentedControl, Select, SimpleGrid, Table, Text, TextInput, Title } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { Can } from "../../components/Can";
import { PageHeader } from "../../components/PageHeader";
import { LEASE_TABS, PageTabs } from "../../components/PageTabs";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import type { Option } from "../purchases/types";
import { LEASES_KEY } from "./types";

interface RentIndex { id: number; code: string; period: string; period_label: string; value: string; source: "insee" | "manual"; fetched_at: string }
interface IndicesResponse { items: RentIndex[]; meta: { indexes: Option[]; insee: string[]; last_fetch: string | null } }
const KEY = ["rent-indices"];

export default function RentIndicesPage() {
  const client = useQueryClient();
  const { data } = useQuery({ queryKey: KEY, queryFn: () => api.get<IndicesResponse>("/api/v1/rent-indices") });
  const [code, setCode] = useState("ILC");
  const [form, setForm] = useState({ code: "FERMAGES", period: "", value: "" });
  const refresh = () => { void client.invalidateQueries({ queryKey: KEY }); void client.invalidateQueries({ queryKey: LEASES_KEY }); };
  const fetchInsee = useAction(() => api.post<{ notices: Notice[] }>("/api/v1/rent-indices/fetch"));
  const save = useAction(() => api.post<{ notices: Notice[] }>("/api/v1/rent-indices", form));
  const remove = useAction((id: number) => api.delete<{ notices: Notice[] }>(`/api/v1/rent-indices/${id}`));
  const rows = (data?.items ?? []).filter((i) => i.code === code);
  const annual = form.code === "FERMAGES";
  return (
    <>
      <PageHeader title="Indices de loyer"
        description="Indices de révision des baux : ILC, ILAT et IRL publiés par l'INSEE, indice national des fermages saisi chaque année."
        actions={<Can><Button loading={fetchInsee.isPending} onClick={() => fetchInsee.mutate(undefined, { onSuccess: refresh })}>
          Mettre à jour depuis l'INSEE</Button></Can>} />
      <PageTabs tabs={LEASE_TABS} />
      <Text size="sm" c="dimmed" mb="sm">Dernière lecture de l'INSEE : {data?.meta.last_fetch ? formatDate(data.meta.last_fetch) : "jamais"}.
        Les révisions dues relisent aussi l'INSEE, au plus une fois par jour.</Text>
      <Paper p="md" mb="md" maw={900}>
        <SegmentedControl mb="sm" value={code} onChange={setCode} data={(data?.meta.indexes ?? []).map((i) => ({ value: i.value, label: i.value }))} />
        <Text size="sm" mb="xs">{data?.meta.indexes.find((i) => i.value === code)?.label}</Text>
        {!rows.length ? <Text size="sm" c="dimmed">Aucune valeur.</Text> : (
          <Table>
            <Table.Thead><Table.Tr><Table.Th>Période</Table.Th><Table.Th ta="right">Valeur</Table.Th><Table.Th>Source</Table.Th><Table.Th /></Table.Tr></Table.Thead>
            <Table.Tbody>{rows.map((r) => (
              <Table.Tr key={r.id}>
                <Table.Td>{r.period_label}</Table.Td>
                <Table.Td ta="right" className="lv-num">{r.value.replace(".", ",")}</Table.Td>
                <Table.Td><StatusBadge tone={r.source === "insee" ? "info" : "neutral"}>{r.source === "insee" ? "INSEE" : "Saisie"}</StatusBadge></Table.Td>
                <Table.Td>{r.source === "manual" && <Can><ActionIcon variant="subtle" color="brique" aria-label={`Supprimer ${r.period_label}`}
                  onClick={() => remove.mutate(r.id, { onSuccess: refresh })}><Trash2 size={16} /></ActionIcon></Can>}</Table.Td>
              </Table.Tr>))}</Table.Tbody>
          </Table>
        )}
      </Paper>
      <Can>
        <Paper p="md" maw={900}>
          <Title order={3} mb="xs">Saisir une valeur</Title>
          <Text size="sm" c="dimmed" mb="sm">Indice des fermages (arrêté ministériel annuel), ou correction d'une valeur de l'INSEE.</Text>
          <SimpleGrid cols={{ base: 1, sm: 4 }}>
            <Select label="Indice" data={(data?.meta.indexes ?? []).map((i) => ({ value: i.value, label: i.value }))} value={form.code}
              allowDeselect={false} onChange={(v) => setForm({ ...form, code: v ?? form.code })} />
            <TextInput label="Période" placeholder={annual ? "2025" : "2025-T2"} value={form.period}
              onChange={(e) => setForm({ ...form, period: e.currentTarget.value })} />
            <TextInput label="Valeur" inputMode="decimal" placeholder="123,06" value={form.value}
              onChange={(e) => setForm({ ...form, value: e.currentTarget.value })} />
            <Group align="flex-end"><Button disabled={!form.period || !form.value} loading={save.isPending}
              onClick={() => save.mutate(undefined, { onSuccess: () => { setForm({ ...form, period: "", value: "" }); refresh(); } })}>Enregistrer</Button></Group>
          </SimpleGrid>
        </Paper>
      </Can>
    </>
  );
}
