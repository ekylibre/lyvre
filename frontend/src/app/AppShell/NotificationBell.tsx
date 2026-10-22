// Cloche de l'en-tête : notifications de fin de tâche en arrière-plan (GET /api/v1/notifications),
// nombre de non lues, liste avec lien vers l'écran concerné, « tout marquer comme lu ». Une
// notification arrivée pendant la session s'affiche aussi en message, sauf si son job est déjà
// suivi à l'écran (JobStatus).
import { useEffect, useRef, useState } from "react";
import { ActionIcon, Button, Group, Indicator, Popover, ScrollArea, Stack, Text, Tooltip, UnstyledButton } from "@mantine/core";
import { notifications as toasts } from "@mantine/notifications";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CircleAlert, CircleCheck, CircleX, Info } from "lucide-react";
import { api } from "../../api/client";
import { isWatchedJob } from "../../api/jobs";
import { useGoTo } from "../navigation";

export const NOTIFICATIONS_KEY = ["notifications"];
const POLL_MS = 30_000;

export interface AppNotification {
  id: number; kind: string; level: "success" | "info" | "warning" | "danger"; title: string; message: string | null;
  url: string | null; job_id: number | null; created_at: string; read: boolean;
}
type Response = { items: AppNotification[]; meta: { unread: number } };

const LEVELS = {
  success: { color: "lichen", icon: CircleCheck },
  info: { color: "ardoise", icon: Info },
  warning: { color: "paille", icon: CircleAlert },
  danger: { color: "brique", icon: CircleX },
} as const;

/** « à l'instant », « il y a 5 min », « il y a 2 h », sinon la date (horodatage serveur en UTC). */
export function ago(iso: string, now = Date.now()): string {
  const at = new Date(`${iso}Z`).getTime();
  const minutes = Math.round((now - at) / 60_000);
  if (minutes < 1) return "à l'instant";
  if (minutes < 60) return `il y a ${minutes} min`;
  if (minutes < 24 * 60) return `il y a ${Math.round(minutes / 60)} h`;
  return new Date(at).toLocaleDateString("fr-FR");
}

export function NotificationBell() {
  const client = useQueryClient();
  const goTo = useGoTo();
  const [opened, setOpened] = useState(false);
  const { data } = useQuery({
    queryKey: NOTIFICATIONS_KEY, refetchInterval: POLL_MS, staleTime: 0,
    queryFn: () => api.get<Response>("/api/v1/notifications?limit=20"),
  });
  const items = data?.items ?? [];
  const unread = data?.meta?.unread ?? 0;

  // Nouvelles notifications depuis le dernier chargement (rien au premier : déjà là avant).
  const seen = useRef<number | null>(null);
  useEffect(() => {
    if (!data?.items) return;
    const max = Math.max(0, ...data.items.map((n) => n.id));
    if (seen.current !== null) {
      for (const n of data.items.filter((x) => x.id > seen.current! && !x.read)) {
        if (n.job_id !== null && isWatchedJob(n.job_id)) continue;
        toasts.show({ color: LEVELS[n.level]?.color ?? "ardoise", title: n.title, message: n.message ?? "",
          autoClose: n.level === "danger" ? false : 8000 });
      }
    }
    seen.current = Math.max(seen.current ?? 0, max);
  }, [data]);

  const markRead = async (ids?: number[]) => {
    const body = await api.post<{ marked: number; meta: { unread: number } }>("/api/v1/notifications/read", ids ? { ids } : {});
    client.setQueryData<Response>(NOTIFICATIONS_KEY, (old) => old && ({
      items: old.items.map((n) => (!ids || ids.includes(n.id) ? { ...n, read: true } : n)), meta: body.meta,
    }));
  };
  const open = (n: AppNotification) => {
    setOpened(false);
    if (!n.read) void markRead([n.id]);
    if (n.url) goTo(n.url);
  };

  return (
    <Popover opened={opened} onChange={setOpened} position="bottom-end" width={380} shadow="md">
      <Popover.Target>
        <Tooltip label="Notifications" disabled={opened}>
          <Indicator label={unread > 9 ? "9+" : unread} size={18} color="brique" disabled={!unread} offset={6}>
            <ActionIcon variant="default" size={44} onClick={() => setOpened((o) => !o)}
              aria-label={unread ? `Notifications : ${unread} non lue(s)` : "Notifications"}>
              <Bell />
            </ActionIcon>
          </Indicator>
        </Tooltip>
      </Popover.Target>
      <Popover.Dropdown p={0}>
        <Group justify="space-between" px="md" py="xs" style={{ borderBottom: "1px solid var(--lv-line)" }}>
          <Text fw={600}>Notifications</Text>
          <Button size="compact-xs" variant="subtle" disabled={!unread} onClick={() => void markRead()}>Tout marquer comme lu</Button>
        </Group>
        {items.length === 0 ? (
          <Text size="sm" c="dimmed" p="md">Aucune notification. Les synchronisations lancées en arrière-plan s'afficheront ici à leur fin.</Text>
        ) : (
          <ScrollArea.Autosize mah={420}>
            <Stack gap={0} role="list" aria-label="Notifications">
              {items.map((n) => {
                const { color, icon: Icon } = LEVELS[n.level] ?? LEVELS.info;
                return (
                  <UnstyledButton key={n.id} role="listitem" onClick={() => open(n)} px="md" py="xs"
                    style={{ borderBottom: "1px solid var(--lv-line)", background: n.read ? undefined : "var(--lv-surface-sunken)" }}
                    aria-label={`${n.read ? "" : "Non lue : "}${n.title}`}>
                    <Group gap="sm" align="flex-start" wrap="nowrap">
                      <Icon size={18} color={`var(--mantine-color-${color}-6)`} style={{ flexShrink: 0, marginTop: 2 }} aria-hidden />
                      <div style={{ minWidth: 0 }}>
                        <Text size="sm" fw={n.read ? 400 : 600}>{n.title}</Text>
                        {n.message && <Text size="xs" c="dimmed" lineClamp={3}>{n.message}</Text>}
                        <Text size="xs" c="dimmed" mt={2}>{ago(n.created_at)}</Text>
                      </div>
                    </Group>
                  </UnstyledButton>
                );
              })}
            </Stack>
          </ScrollArea.Autosize>
        )}
      </Popover.Dropdown>
    </Popover>
  );
}
