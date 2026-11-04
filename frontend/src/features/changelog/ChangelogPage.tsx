// Menu utilisateur › Nouveautés (lot R2) : versions publiées de Lyvre, la plus récente en tête ;
// actions requises en tête de version, étiquette « Associations » / « SCI » sur les entrées propres à
// une structure. Ouvrir la page retire le repère « nouveau ».
import { useEffect } from "react";
import { Alert, Badge, Center, Group, List, Loader, Paper, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { usePreferences } from "../../api/session";
import { PageHeader } from "../../components/PageHeader";
import { formatDate } from "../../lib/format";

type Kind = "action" | "new" | "improved" | "fixed";
interface Entry { kind: Kind; structure?: "asso" | "sci" | "societe" | "agri"; text: string }
interface Release { version: string; date: string; title: string; entries: Entry[] }

const SECTIONS: { kind: Exclude<Kind, "action">; label: string }[] = [
  { kind: "new", label: "Nouveautés" }, { kind: "improved", label: "Améliorations" }, { kind: "fixed", label: "Corrections" },
];
const STRUCTURES = { asso: "Associations", sci: "SCI", societe: "Sociétés", agri: "Exploitations agricoles" };
const STRUCTURE_COLORS = { asso: "lichen", sci: "ardoise", societe: "gray", agri: "paille" };

function Item({ entry }: { entry: Entry }) {
  return (
    <List.Item>
      {entry.structure && <Badge size="xs" variant="light" color={STRUCTURE_COLORS[entry.structure]} mr={6}>
        {STRUCTURES[entry.structure]}</Badge>}
      {entry.text}
    </List.Item>
  );
}

export default function ChangelogPage() {
  const { data, isPending } = useQuery({ queryKey: ["changelog"],
    queryFn: () => api.get<{ items: Release[]; version: string }>("/api/v1/changelog") });
  const [preferences, update] = usePreferences();
  useEffect(() => {
    if (data && preferences.changelog_seen !== data.version) update({ changelog_seen: data.version });
  }, [data, preferences.changelog_seen, update]);
  if (isPending || !data) return <Center h={300}><Loader /></Center>;

  return (
    <>
      <PageHeader title="Nouveautés" description={`Lyvre ${data.version} : ce qui a changé, version par version.`} />
      <Stack maw={820}>
        {data.items.map((release, i) => {
          const actions = release.entries.filter((e) => e.kind === "action");
          return (
            <Paper key={release.version} p="md">
              <Group justify="space-between" mb="xs" align="baseline">
                <Group gap="xs" align="baseline">
                  <Title order={2} size="h4">{release.title}</Title>
                  {i === 0 && <Badge size="sm" variant="light" color="lichen">Version actuelle</Badge>}
                </Group>
                <Text size="sm" c="dimmed" className="lv-num">{release.version} · {formatDate(release.date)}</Text>
              </Group>
              {actions.length > 0 && (
                <Alert color="paille" title="Action requise" mb="xs">
                  <List size="sm" spacing={4}>{actions.map((e) => <Item key={e.text} entry={e} />)}</List>
                </Alert>
              )}
              {SECTIONS.map(({ kind, label }) => {
                const items = release.entries.filter((e) => e.kind === kind);
                return items.length > 0 && (
                  <Stack key={kind} gap={4} mb={6}>
                    <Text size="xs" fw={600} c="dimmed" tt="uppercase">{label}</Text>
                    <List size="sm" spacing={4}>{items.map((e) => <Item key={e.text} entry={e} />)}</List>
                  </Stack>
                );
              })}
            </Paper>
          );
        })}
      </Stack>
    </>
  );
}
