// Compta › Déclarations de TVA (lot T3) : mois de l'exercice déclarant, statut, échéance, retard, TVA à
// payer ou crédit ; ouvrir un mois pour préparer, valider et déposer sa CA3.
import { Alert, Button, Center, Loader, Select, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { DataGrid } from "../../components/DataGrid";
import { AppLink } from "../../app/navigation";
import { formatDate } from "../../lib/format";
import { InstallmentsPanel } from "./InstallmentsPanel";
import { STATUS_TONES, VAT_RETURNS_KEY, monthLabel, type PeriodRow, type VatReturnsList } from "./types";

export default function VatReturnsPage() {
  const [params, setParams] = useUrlParams({ fiscal_year_id: "" });
  const url = `/api/v1/vat-returns${params.fiscal_year_id ? `?fiscal_year_id=${params.fiscal_year_id}` : ""}`;
  const { data } = useQuery({ queryKey: [...VAT_RETURNS_KEY, url], queryFn: () => api.get<VatReturnsList>(url) });
  if (!data) return <Center h={300}><Loader /></Center>;
  const late = data.items.filter((row) => row.late).length;
  return (
    <>
      <PageHeader title="Déclarations de TVA"
        description={data.fiscal_year?.vat_period === "annual"
          ? "CA12A annuelle et acomptes trimestriels (3525 bis) calculés depuis les écritures, à saisir sur l'espace professionnel puis à marquer déposés."
          : "CA3 calculée depuis les écritures, à saisir sur TeleDEC puis à marquer déposée."}
        actions={data.fiscal_year && <Button variant="default" component={AppLink}
          href={data.fiscal_year.vat_period === "annual" ? `/vat-returns/books?period=${data.items[0]?.period ?? ""}` : "/vat-returns/books"}>
          Livres de TVA</Button>} />
      {data.fiscal_year === null ? (
        <Alert color="paille">Aucun exercice ne prépare sa déclaration de TVA dans Lyvre : activez « Déclaration mensuelle
          (CA3) » sur l'exercice (Compta › Exercices), après l'avoir déclaré soumis à la TVA.</Alert>
      ) : (
        <>
          <FilterBar>
            <Select aria-label="Exercice" w={200} allowDeselect={false} value={String(data.fiscal_year.id)}
              data={data.fiscal_years.map((y) => ({ value: y.value, label: `Exercice ${y.label}` }))}
              onChange={(v) => setParams({ fiscal_year_id: v ?? "" })} />
          </FilterBar>
          {late > 0 && <Alert color="brique" mb="md">{late} déclaration{late > 1 ? "s" : ""} en retard : préparez-les dans
            l'ordre des mois, le crédit de chaque mois se reporte sur le suivant.</Alert>}
          <DataGrid<PeriodRow> id="vat-returns" records={data.items} idAccessor="period" columns={[
            { accessor: "period", title: "Période", render: (row) => <AppLink href={`/vat-returns/${row.period}`}>{monthLabel(row.period)}</AppLink> },
            { accessor: "status", title: "Statut", render: (row) => (
              <StatusBadge tone={row.late ? "gap" : STATUS_TONES[row.status]}>{row.late ? `${row.status_label} — en retard` : row.status_label}</StatusBadge>) },
            { accessor: "deadline", title: "Échéance", render: (row) => <span className="lv-num">{formatDate(row.deadline)}</span> },
            { accessor: "amount", title: "À payer / crédit", textAlign: "right", render: (row) => !row.return
              ? <Text size="sm" c="dimmed">—</Text>
              : row.return.due_cents ? <MoneyText cents={row.return.due_cents} />
                : row.return.credit_cents ? <Text size="sm">crédit <MoneyText cents={row.return.credit_cents} /></Text>
                  : <Text size="sm" c="dimmed">néant</Text> },
            { accessor: "declared", title: "Dépôt", render: (row) => row.return?.declared_on
              ? <span className="lv-num">{formatDate(row.return.declared_on)}</span> : <Text size="sm" c="dimmed">—</Text> },
          ]} />
          {data.fiscal_year.vat_period === "annual" && data.items.map((row) => (
            <InstallmentsPanel key={row.period} period={row.period} />))}
        </>
      )}
    </>
  );
}
