// Cadre commun des états : titre, exercice (URL), impression, exports éventuels.
import type { ReactNode } from "react";
import { Alert, Button, Center, Loader, Select, Text } from "@mantine/core";
import { Printer } from "lucide-react";
import { FilterBar } from "../../components/FilterBar";
import { PageHeader } from "../../components/PageHeader";
import { formatDate } from "../../lib/format";

export interface FiscalYearRef { id: number; label: string; start_date: string; end_date: string }
export interface ReportMeta {
  fiscal_years: { value: string; label: string }[];
  fiscal_year: FiscalYearRef | null;
  previous: FiscalYearRef | null;
}

export function ReportFrame({ title, meta, fyId, onFyChange, actions, filters, loading, children }: {
  title: string; meta: ReportMeta | undefined; fyId: string; onFyChange: (id: string) => void;
  actions?: ReactNode; filters?: ReactNode; loading: boolean; children: ReactNode;
}) {
  const fy = meta?.fiscal_year;
  return (
    <>
      <PageHeader title={title}
        description={fy ? `Exercice ${fy.label} (${formatDate(fy.start_date)} – ${formatDate(fy.end_date)})`
          + (meta?.previous ? `, comparé à ${meta.previous.label}` : "") : undefined}
        actions={<>{actions}<Button variant="default" leftSection={<Printer size={18} />} onClick={() => window.print()}>Imprimer</Button></>} />
      <FilterBar>
        <Select label="Exercice" data={meta?.fiscal_years ?? []} value={fyId || (fy ? String(fy.id) : null)} w={180}
          allowDeselect={false} onChange={(v) => onFyChange(v ?? "")} />
        {filters}
      </FilterBar>
      {loading && !meta ? <Center h={200}><Loader /></Center>
        : !fy ? <Alert color="paille">Aucun exercice ouvert : créez-en un dans Compta › Exercices.</Alert>
          : children}
      <Text size="xs" c="dimmed" mt="md" className="lv-print-only">Imprimé le {new Date().toLocaleDateString("fr-FR")}</Text>
    </>
  );
}
