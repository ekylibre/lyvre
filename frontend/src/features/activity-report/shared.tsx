// Rapport d'activité : exercice choisi (?fy_id=), sélecteur commun aux écrans.
import { Select } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useUrlParams } from "../../components/FilterBar";

export const REPORT_KEY = ["activity-report"];

export interface ReportContext {
  fiscal_years: { value: string; label: string }[];
  fiscal_year: { id: number; label: string };
  prorata: boolean;
  links: { preview: string; pdf: string; html: string; docx: string; odt: string };
}

/** Exercice et mode éco de l'URL ; le contexte donne l'exercice effectif (le plus récent par défaut). */
export function useReportContext() {
  const [params, setParams] = useUrlParams({ fy_id: "", prorata: "" });
  const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
  const context = useQuery({ queryKey: [...REPORT_KEY, "context", query], retry: false, placeholderData: (prev) => prev,
    queryFn: () => api.get<ReportContext>(`/api/v1/activity-report${query ? `?${query}` : ""}`) });
  return { params, setParams, context };
}

export function FiscalYearSelect({ context, onChange }: { context: ReportContext | undefined; onChange: (fyId: string) => void }) {
  return (
    <Select label="Exercice" data={context?.fiscal_years ?? []} value={context ? String(context.fiscal_year.id) : null}
      allowDeselect={false} w={160} onChange={(v) => v && onChange(v)} />
  );
}

export const withFy = (path: string, fyId: number | undefined) => (fyId ? `${path}?fy_id=${fyId}` : path);
