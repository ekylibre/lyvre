// Indicateurs › Facteurs d'impact (admin) : conversion ventes → kg, CO₂, eau ; source ADEME.
import { useEffect, useState } from "react";
import { Alert, Anchor, Button, Center, Loader, NumberInput, Table, Text, TextInput } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { PageHeader } from "../../components/PageHeader";
import { AppLink } from "../../app/navigation";
import { IMPACT_KEY } from "./types";

interface Factor { id: number; key: string; value: number | string; unit: string; source_label: string; source_url: string }

export default function FactorsPage() {
  const key = [...IMPACT_KEY, "factors"];
  const { data } = useQuery({ queryKey: key, queryFn: () => api.get<{ items: Factor[] }>("/api/v1/impact/factors") });
  const [rows, setRows] = useState<Factor[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  useEffect(() => { if (data) setRows(data.items); }, [data]);
  const save = useAction(() => api.put<{ notices: Notice[] }>("/api/v1/impact/factors", { items: rows }),
    { invalidate: [IMPACT_KEY], silent: true });
  const set = (id: number, patch: Partial<Factor>) => setRows(rows.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  if (!data) return <Center h={300}><Loader /></Center>;
  return (
    <>
      <PageHeader title="Facteurs d'impact environnemental" description="Conversion ventes → kg, CO₂, eau. Source : ADEME Base Empreinte."
        actions={<Button variant="default" component={AppLink} href="/impact/">Tableau de bord</Button>} />
      <Alert color="ardoise" variant="light" mb="md">
        Les valeurs par défaut sont des ordres de grandeur <b>à valider</b> par le bureau à partir de la{" "}
        <Anchor href="https://base-empreinte.ademe.fr" target="_blank" rel="noopener">Base Empreinte ADEME</Anchor> avant toute
        communication externe.
      </Alert>
      <form onSubmit={(e) => {
        e.preventDefault(); setErrors({});
        save.mutate(undefined, { onError: (err) => setErrors(err instanceof ApiError ? err.fields : {}) });
      }}>
        <Table.ScrollContainer minWidth={760}>
          <Table>
            <Table.Thead><Table.Tr><Table.Th>Facteur</Table.Th><Table.Th w={170}>Valeur</Table.Th><Table.Th>Unité</Table.Th>
              <Table.Th>Source</Table.Th><Table.Th>Adresse</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>{rows.map((f) => (
              <Table.Tr key={f.id}>
                <Table.Td><Text size="sm" className="lv-num">{f.key}</Text></Table.Td>
                <Table.Td><NumberInput aria-label={`Valeur de ${f.key}`} value={f.value} decimalSeparator="," decimalScale={6} hideControls
                  error={errors[`value_${f.id}`]} onChange={(v) => set(f.id, { value: v })} /></Table.Td>
                <Table.Td><Text size="sm" c="dimmed">{f.unit}</Text></Table.Td>
                <Table.Td><TextInput aria-label={`Source de ${f.key}`} value={f.source_label} maxLength={200}
                  onChange={(e) => set(f.id, { source_label: e.currentTarget.value })} /></Table.Td>
                <Table.Td><TextInput aria-label={`Adresse de la source de ${f.key}`} type="url" value={f.source_url} maxLength={500}
                  error={errors[`source_url_${f.id}`]} onChange={(e) => set(f.id, { source_url: e.currentTarget.value })} /></Table.Td>
              </Table.Tr>
            ))}</Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        <Button type="submit" mt="sm" loading={save.isPending}>Enregistrer</Button>
      </form>
    </>
  );
}
