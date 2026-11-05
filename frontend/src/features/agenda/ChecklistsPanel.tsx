// Échéancier › listes de contrôle guidées (lot AG9b.e, AG9.6) : clôture, campagne PAC, mois fiscal de mai, automne.
// Sans IA : chaque étape renvoie vers son écran ; certaines se cochent d'après le dossier, les autres à la main.
import { Anchor, Badge, Checkbox, Group, Paper, Progress, SimpleGrid, Stack, Text, Title, Tooltip } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useCan } from "../../api/session";
import { AppLink } from "../../app/navigation";

interface Step { id: string; label: string; link: string | null; fiche: string | null; auto: boolean; auto_done: boolean | null;
  marked_on: string | null; done: boolean }
export interface Checklist { id: string; title: string; summary: string | null; period: string; start: string; end: string;
  status: "current" | "upcoming"; profile_incomplete: boolean; progress: { done: number; total: number }; steps: Step[] }

const day = (iso: string) => new Date(iso).toLocaleDateString("fr-FR");

export function ChecklistsPanel() {
  const can = useCan();
  const { data } = useQuery({ queryKey: ["agenda", "checklists"], queryFn: () => api.get<{ item: { items: Checklist[] } }>("/api/v1/checklists") });
  const mark = useAction(({ c, step, done }: { c: Checklist; step: string; done: boolean }) =>
    api.put<{ notices: Notice[] }>(`/api/v1/checklists/${c.id}/${encodeURIComponent(c.period)}/steps/${step}`, { done }), { invalidate: [["agenda", "checklists"]] });
  const items = Array.isArray(data?.item?.items) ? data.item.items : [];
  if (!items.length) return null;
  return (
    <SimpleGrid cols={{ base: 1, md: Math.min(items.length, 2) }} mb="md">
      {items.map((c) => (
        <Paper key={`${c.id}-${c.period}`} withBorder p="md">
          <Group justify="space-between" mb={4}>
            <Title order={5}>{c.title} {c.period}</Title>
            <Badge variant="light" color={c.status === "current" ? "lichen" : "gray"}>
              {c.status === "current" ? `jusqu'au ${day(c.end)}` : `à partir du ${day(c.start)}`}</Badge>
          </Group>
          {c.summary && <Text size="xs" c="dimmed">{c.summary}</Text>}
          {c.profile_incomplete && <Text size="xs" c="paille">Profil à compléter pour savoir si cette liste vous concerne.</Text>}
          <Progress my={6} value={c.progress.total ? (100 * c.progress.done) / c.progress.total : 0} />
          <Stack gap={4}>
            {c.steps.map((s) => (
              <Group key={s.id} gap="xs" wrap="nowrap" align="flex-start">
                <Tooltip label={s.auto ? (s.auto_done ? "Constaté dans Lyvre" : "Contrôlé par Lyvre : pas encore fait") : "À cocher"} withArrow>
                  <Checkbox aria-label={s.label} size="xs" mt={2} checked={s.done} disabled={!can.write || (s.auto && !!s.auto_done)}
                    onChange={(e) => mark.mutate({ c, step: s.id, done: e.currentTarget.checked })} />
                </Tooltip>
                <Text size="sm" td={s.done ? "line-through" : undefined} c={s.done ? "dimmed" : undefined}>
                  {s.link ? <Anchor component={AppLink} href={s.link} size="sm" inherit>{s.label}</Anchor> : s.label}
                  {s.fiche && <Badge ml={6} size="xs" variant="outline" color="gray">{s.fiche}</Badge>}
                  {s.auto && <Text span size="xs" c="dimmed"> · auto</Text>}
                </Text>
              </Group>))}
          </Stack>
        </Paper>))}
    </SimpleGrid>
  );
}
