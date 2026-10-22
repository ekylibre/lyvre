// Imports › Tonnages éco-organismes (admin) : import de la déclaration (.xlsx, feuille « Bilan »)
// et correction des tonnages (entrant = collecté, sortant = réemployé) par trimestre.
import { useEffect, useState } from "react";
import { Alert, Button, Checkbox, Group, NumberInput, Progress, Stack, Table, Text } from "@mantine/core";
import { Dropzone } from "@mantine/dropzone";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp } from "lucide-react";
import { api, ApiError } from "../../api/client";
import { showNotices, useAction, type Notice } from "../../api/resources";
import { upload } from "../../api/upload";
import { PageHeader } from "../../components/PageHeader";
import { AppLink } from "../../app/navigation";
import { REPORT_KEY } from "./shared";

interface Row {
  id: number; organism: string; material: string; quarter: string; entrant_t: number | string; sortant_t: number | string;
  financing_cents: number; source: string; delete?: boolean;
}

export default function EcoPage() {
  const client = useQueryClient();
  const key = [...REPORT_KEY, "eco"];
  const { data } = useQuery({ queryKey: key, queryFn: () => api.get<{ items: Row[] }>("/api/v1/activity-report/eco") });
  const [rows, setRows] = useState<Row[]>([]);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (data) setRows(data.items); }, [data]);
  const set = (id: number, patch: Partial<Row>) => setRows(rows.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  const original = new Map((data?.items ?? []).map((r) => [r.id, r]));
  const changed = rows.filter((r) => {
    const o = original.get(r.id);
    return r.delete || !o || o.entrant_t !== r.entrant_t || o.sortant_t !== r.sortant_t || o.financing_cents !== r.financing_cents;
  });
  const save = useAction(() => api.put<{ notices: Notice[] }>("/api/v1/activity-report/eco", { rows: changed }),
    { invalidate: [key, REPORT_KEY] });

  const send = async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    setError(null); setProgress(0);
    try {
      const body = await upload<{ notices: Notice[] }>("/api/v1/activity-report/eco/import", form, setProgress);
      showNotices(body.notices);
      void client.invalidateQueries({ queryKey: REPORT_KEY });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "L'import a échoué.");
    } finally {
      setProgress(null);
    }
  };

  return (
    <>
      <PageHeader title="Tonnages éco-organismes" description="Ecomaison, Ecologic : collecté (entrant) et réemployé (sortant), par trimestre."
        actions={<Button variant="default" component={AppLink} href="/rapport-activite/">Rapport</Button>} />
      <Stack maw={720} mb="lg">
        <Dropzone onDrop={(files) => files[0] && void send(files[0])} multiple={false} loading={progress !== null}
          accept={{ "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"] }}
          onReject={() => setError("Fichier refusé : .xlsx attendu.")}>
          <Group justify="center" mih={100} style={{ pointerEvents: "none" }}>
            <FileUp size={32} />
            <div><Text fw={600}>Déposer la déclaration (.xlsx) ici ou cliquer pour la choisir</Text>
              <Text size="sm" c="dimmed">Feuille « Bilan » ; les lignes existantes sont mises à jour (organisme, matière, trimestre).</Text></div>
          </Group>
        </Dropzone>
        {progress !== null && <Progress value={progress} aria-label="Envoi du fichier" />}
        {error && <Alert color="brique" role="alert">{error}</Alert>}
      </Stack>
      {rows.length ? (
        <form onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
          <Table.ScrollContainer minWidth={820}>
            <Table>
              <Table.Thead><Table.Tr><Table.Th>Organisme</Table.Th><Table.Th>Matière</Table.Th><Table.Th>Trimestre</Table.Th>
                <Table.Th ta="right">Entrant (t)</Table.Th><Table.Th ta="right">Sortant (t)</Table.Th><Table.Th ta="right">Financement (€)</Table.Th>
                <Table.Th>Source</Table.Th><Table.Th>Supprimer</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>{rows.map((r) => {
                const label = `${r.organism} ${r.material} ${r.quarter}`;
                const num = (field: "entrant_t" | "sortant_t", aria: string) => (
                  <NumberInput aria-label={`${aria} ${label}`} value={r[field]} min={0} decimalScale={3} decimalSeparator="," hideControls w={110}
                    classNames={{ input: "lv-num" }} styles={{ input: { textAlign: "right" } }} disabled={r.delete}
                    onChange={(v) => set(r.id, { [field]: v === "" ? 0 : v })} />
                );
                return (
                  <Table.Tr key={r.id} style={{ opacity: r.delete ? 0.5 : 1 }}>
                    <Table.Td>{r.organism}</Table.Td><Table.Td>{r.material}</Table.Td><Table.Td>{r.quarter}</Table.Td>
                    <Table.Td>{num("entrant_t", "Entrant")}</Table.Td><Table.Td>{num("sortant_t", "Sortant")}</Table.Td>
                    <Table.Td><NumberInput aria-label={`Financement ${label}`} value={r.financing_cents / 100} min={0} decimalScale={2} fixedDecimalScale
                      decimalSeparator="," thousandSeparator=" " hideControls w={120} classNames={{ input: "lv-num" }} styles={{ input: { textAlign: "right" } }}
                      disabled={r.delete} onChange={(v) => set(r.id, { financing_cents: Math.round(Number(v || 0) * 100) })} /></Table.Td>
                    <Table.Td><Text size="sm" c="dimmed">{r.source}</Text></Table.Td>
                    <Table.Td><Checkbox aria-label={`Supprimer ${label}`} checked={r.delete ?? false}
                      onChange={(e) => set(r.id, { delete: e.currentTarget.checked })} /></Table.Td>
                  </Table.Tr>
                );
              })}</Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          <Button type="submit" mt="sm" loading={save.isPending} disabled={!changed.length}>
            Enregistrer{changed.length ? ` (${changed.length})` : ""}</Button>
        </form>
      ) : data && <Alert color="ardoise" variant="light">Aucun tonnage. Importez la déclaration éco-organismes ci-dessus.</Alert>}
    </>
  );
}
