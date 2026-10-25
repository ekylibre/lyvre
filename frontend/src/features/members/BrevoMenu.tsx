// Adhérents › Brevo (lot B3) : aperçu et synchronisation de la liste Brevo, dernier passage. La
// première synchronisation passe obligatoirement par un aperçu, validé depuis son rapport.
import { Button, Menu, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { useIntegration } from "../../api/session";
import { Can } from "../../components/Can";
import { AppLink, useGoTo } from "../../app/navigation";
import { localDateTime } from "../integrations/types";

export interface BrevoStatus {
  enabled: boolean; configured: boolean; first_sync_pending: boolean; links: number; conflicts: number;
  last_job: { id: number; status: string; message: string | null; finished_at: string | null } | null;
}
export const BREVO_STATUS_KEY = ["brevo", "status"];

export function useStartBrevoSync() {
  const goTo = useGoTo();
  const start = useAction((dryRun: boolean) => api.post<{ job: { id: number }; notices?: Notice[] }>("/api/v1/brevo/sync", { dry_run: dryRun }),
    { invalidate: [BREVO_STATUS_KEY] });
  return { ...start, run: (dryRun: boolean) => start.mutate(dryRun, { onSuccess: (r) => goTo(`/entities/members/brevo/${r.job.id}`) }) };
}

export function BrevoMenu() {
  const enabled = useIntegration("brevo");
  const status = useQuery({ queryKey: BREVO_STATUS_KEY, enabled,
    queryFn: () => api.get<BrevoStatus>("/api/v1/brevo/status") });
  const start = useStartBrevoSync();
  if (!enabled || !status.data) return null;
  const s = status.data;
  return (
    <Can>
      <Menu position="bottom-end">
        <Menu.Target>
          <Button variant="default" loading={start.isPending} rightSection={<ChevronDown size={16} />}>Brevo</Button>
        </Menu.Target>
        <Menu.Dropdown maw={320}>
          <Menu.Item onClick={() => start.run(true)}>Aperçu (sans rien écrire)</Menu.Item>
          <Menu.Item disabled={s.first_sync_pending || !s.configured} onClick={() => start.run(false)}>
            Synchroniser avec Brevo</Menu.Item>
          <Menu.Divider />
          <Menu.Label>
            {s.first_sync_pending ? "Première synchronisation : lancez d'abord l'aperçu."
              : `${s.links} adhérent(s) lié(s)${s.conflicts ? `, ${s.conflicts} conflit(s)` : ""}`}
          </Menu.Label>
          {s.last_job && (
            <Menu.Item component={AppLink} href={`/entities/members/brevo/${s.last_job.id}`}>
              <Text size="sm">Dernier passage</Text>
              <Text size="xs" c="dimmed">{s.last_job.finished_at ? localDateTime(s.last_job.finished_at) : "en cours"}</Text>
            </Menu.Item>
          )}
        </Menu.Dropdown>
      </Menu>
    </Can>
  );
}
