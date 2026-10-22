// Suivi d'une tâche longue (synchronisation en arrière-plan) : GET /api/v1/jobs/<id> toutes
// les secondes tant qu'elle tourne ; `onDone` à la fin (rechargement des listes).
import { useEffect, useRef, type ReactNode } from "react";
import { Alert, Progress, Text } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { watchJob } from "../api/jobs";
import { formatDate } from "../lib/format";

export interface Job {
  id: number; kind: string; status: "running" | "done" | "failed"; message: string | null;
  progress_done: number; progress_total: number | null; result: Record<string, unknown> | null;
  finished_at: string | null;
}

export function JobStatus({ job, onDone, renderResult }: {
  job: Job;
  onDone?: (job: Job) => void;
  renderResult?: (result: Record<string, unknown>) => ReactNode;
}) {
  const { data } = useQuery({
    queryKey: ["jobs", job.id], initialData: { job },
    queryFn: () => api.get<{ job: Job }>(`/api/v1/jobs/${job.id}`),
    refetchInterval: (query) => (query.state.data?.job.status === "running" ? 1000 : false),
  });
  const current = data.job;
  const client = useQueryClient();
  useEffect(() => watchJob(job.id), [job.id]);
  const reported = useRef(current.status !== "running");
  useEffect(() => {
    if (current.status !== "running" && !reported.current) {
      reported.current = true;
      onDone?.(current);
      // La notification de fin vient d'être créée : la cloche se met à jour sans attendre.
      void client.invalidateQueries({ queryKey: ["notifications"] });
    }
  }, [current, onDone, client]);

  const color = current.status === "running" ? "ardoise" : current.status === "done" ? "lichen" : "brique";
  const title = current.status === "running" ? "Synchronisation en cours…"
    : current.status === "done" ? "Synchronisation terminée" : "La synchronisation a échoué";
  return (
    <Alert color={color} variant="light" role={current.status === "failed" ? "alert" : "status"} title={title} mb="sm">
      {current.status === "running" ? (
        <>
          {current.message && <Text size="sm">{current.message}</Text>}
          {current.progress_total ? (
            <><Progress value={(100 * current.progress_done) / current.progress_total} mt={6} animated aria-label="Progression" />
              <Text size="xs" c="dimmed">{current.progress_done} / {current.progress_total}</Text></>
          ) : <Text size="xs" c="dimmed">{current.progress_done} traité(s)</Text>}
        </>
      ) : (
        <>
          {current.status === "done" && current.result && renderResult ? renderResult(current.result) : current.message && <Text size="sm">{current.message}</Text>}
          {current.finished_at && <Text size="xs" c="dimmed">Terminée le {formatDate(current.finished_at)} à {current.finished_at.slice(11, 16)}</Text>}
        </>
      )}
    </Alert>
  );
}
