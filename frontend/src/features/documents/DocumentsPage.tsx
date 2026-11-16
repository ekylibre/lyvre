// Documents (lot NV5, claudedocs/design_navigation.md § 6) : navigateur en lecture seule des fichiers stockés pour
// l'instance. Types et exercices à gauche (compteurs), tableau au centre, aperçu PDF ou image en tiroir.
// Les fichiers sont servis par la route existante de chaque fiche d'origine (mêmes droits).
import { useState } from "react";
import {
  Anchor, Button, Drawer, Grid, Group, NavLink, Paper, Stack, Text, Title,
} from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Download, ExternalLink } from "lucide-react";
import { api } from "../../api/client";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FilterBar, SearchInput, useUrlParams } from "../../components/FilterBar";
import { IconTile } from "../../components/IconTile";
import { PageHeader } from "../../components/PageHeader";
import { AppLink } from "../../app/navigation";
import { formatDate } from "../../lib/format";

export interface DocumentRow {
  id: string; kind: string; kind_label: string; name: string; date: string | null; size: number | null;
  mime: string | null; party: string | null; fiscal_year: { id: number; label: string } | null;
  origin: { label: string; url: string }; file_url: string; preview: boolean;
}
interface Facet { value: string; label: string; count: number; icon?: string; pictogram?: string | null }
interface DocumentsData {
  items: DocumentRow[]; total: number; page: number; page_size: number;
  facets: { kinds: Facet[]; fiscal_years: Facet[] };
}

export function formatSize(bytes: number | null): string {
  if (bytes === null) return "";
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} Ko`;
  return `${(bytes / (1024 * 1024)).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} Mo`;
}


function Preview({ doc, onClose }: { doc: DocumentRow | null; onClose: () => void }) {
  return (
    <Drawer opened={!!doc} onClose={onClose} position="right" size="xl" title={doc?.name}>
      {doc && (
        <Stack>
          <Group gap="xs">
            <Button component="a" href={doc.file_url} download={doc.name} leftSection={<Download size={16} />} variant="default">
              Télécharger
            </Button>
            <Button component={AppLink} href={doc.origin.url} leftSection={<ExternalLink size={16} />} variant="subtle">
              Ouvrir la fiche
            </Button>
          </Group>
          <Text size="sm" c="dimmed">
            {doc.kind_label} · {doc.origin.label}{doc.party && ` · ${doc.party}`}{doc.date && ` · ${formatDate(doc.date)}`}
          </Text>
          {!doc.preview ? <Text size="sm">Pas d'aperçu pour ce type de fichier : téléchargez-le.</Text>
            : doc.mime?.startsWith("image/")
              ? <img src={doc.file_url} alt={doc.name} style={{ maxWidth: "100%" }} />
              : <iframe src={doc.file_url} title={`Aperçu de ${doc.name}`}
                  style={{ width: "100%", height: "75vh", border: 0 }} />}
        </Stack>
      )}
    </Drawer>
  );
}

export default function DocumentsPage() {
  const [params, setParams] = useUrlParams({ kind: "", fiscal_year: "", q: "", page: "" });
  const [current, setCurrent] = useState<DocumentRow | null>(null);
  const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
  const { data, isFetching } = useQuery({
    queryKey: ["documents", query], placeholderData: (prev) => prev,
    queryFn: () => api.get<DocumentsData>(`/api/v1/documents${query ? `?${query}` : ""}`),
  });
  const kinds = data?.facets.kinds ?? [];
  const kindOf = Object.fromEntries(kinds.map((k) => [k.value, k]));
  const columns: GridColumn<DocumentRow>[] = [
    { accessor: "name", title: "Document", hideable: false, render: (d) => (
      <Group gap="xs" wrap="nowrap">
        <IconTile icon={kindOf[d.kind]?.icon} pictogram={kindOf[d.kind]?.pictogram ?? undefined} size={28} />
        <Anchor component="button" type="button" size="sm" onClick={() => setCurrent(d)} ta="left">{d.name}</Anchor>
      </Group>
    ) },
    { accessor: "kind_label", title: "Type" },
    { accessor: "date", title: "Date", render: (d) => formatDate(d.date) },
    { accessor: "party", title: "Tiers" },
    { accessor: "size", title: "Taille", textAlign: "right", render: (d) => formatSize(d.size) },
    { accessor: "origin", title: "Fiche", render: (d) => (
      <Anchor component={AppLink} href={d.origin.url} size="sm">{d.origin.label}</Anchor>
    ) },
  ];
  const facet = (key: "kind" | "fiscal_year", f: Facet) => {
    const active = params[key] === f.value;
    return (
      <NavLink key={f.value} label={f.label} active={active} aria-current={active ? "true" : undefined}
        leftSection={key === "kind" ? <IconTile icon={f.icon} pictogram={f.pictogram ?? undefined} size={24} /> : undefined}
        rightSection={<Text size="xs" c="dimmed">{f.count}</Text>}
        onClick={() => setParams({ [key]: active ? "" : f.value, page: "" })} />
    );
  };
  const total = data?.total ?? 0;
  return (
    <>
      <PageHeader title="Documents"
        description="Les fichiers déjà enregistrés dans Lyvre, en lecture seule. Chaque document s'ouvre depuis sa fiche d'origine." />
      <FilterBar>
        <SearchInput value={params.q} onChange={(q) => setParams({ q, page: "" })} placeholder="Nom, tiers ou fiche…" />
      </FilterBar>
      <Grid>
        <Grid.Col span={{ base: 12, md: 3 }}>
          <Paper p="xs" withBorder>
            <Title order={2} size="h5" px="xs" mb={4}>Types</Title>
            {kinds.length === 0 && <Text size="sm" c="dimmed" px="xs">Aucun document.</Text>}
            {kinds.map((k) => facet("kind", k))}
            {(data?.facets.fiscal_years.length ?? 0) > 0 && <Title order={2} size="h5" px="xs" mt="md" mb={4}>Exercices</Title>}
            {data?.facets.fiscal_years.map((f) => facet("fiscal_year", f))}
          </Paper>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 9 }}>
          <DataGrid id="documents" records={data?.items} columns={columns} fetching={isFetching}
            onRowClick={setCurrent}
            pagination={total > (data?.page_size ?? 50) ? { page: Number(params.page) || 1, perPage: data?.page_size ?? 50,
              total, onPageChange: (page) => setParams({ page: String(page) }) } : undefined}
            emptyText={params.kind && kindOf[params.kind] ? `Aucun document « ${kindOf[params.kind].label} » pour ce filtre.`
              : "Aucun document pour ce filtre."} />
        </Grid.Col>
      </Grid>
      <Preview doc={current} onClose={() => setCurrent(null)} />
    </>
  );
}
