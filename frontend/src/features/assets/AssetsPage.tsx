// Compta › Immobilisations (lot F5) : registre (valeur d'origine, cumul des amortissements, valeur
// nette), création d'une fiche ; tableau de l'annexe dans l'assistant de clôture.
import { useState } from "react";
import { Alert, Anchor, Button, Checkbox, Select, Text } from "@mantine/core";
import { useList } from "../../api/resources";
import { Can } from "../../components/Can";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { FormModal } from "../../components/FormModal";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink, useGoTo } from "../../app/navigation";
import { AssetForm, type AssetDraft } from "./AssetForm";
import { LedgerGapsCard } from "./LedgerGapsCard";
import { useCan } from "../../api/session";
import { ReinvestmentsPanel } from "./ReinvestmentsPanel";
import { ASSETS_KEY, STATUS_TONES, type AssetItem, type AssetsMeta } from "./types";
import { CalculatorLink } from "../tools/CalculatorLink";

const COLUMNS: GridColumn<AssetItem>[] = [
  { accessor: "label", title: "Immobilisation", hideable: false, render: (a) => <Anchor component={AppLink} href={`/assets/${a.id}`} size="sm">{a.label}</Anchor> },
  { accessor: "account", title: "Compte", render: (a) => <span className="lv-num">{a.account.code}</span> },
  { accessor: "living", title: "Effectif", textAlign: "right", render: (a) => a.living?.units != null
    ? <Text size="sm">{a.living.units}{a.living.species ? ` · ${a.living.species}` : ""}</Text> : null },
  { accessor: "in_service_date", title: "Mise en service", render: (a) => <span className="lv-num">{formatDate(a.in_service_date ?? "")}</span> },
  { accessor: "method_label", title: "Plan", render: (a) => <Text size="sm">{a.method_label}{a.duration_months ? ` · ${a.duration_months} mois` : ""}{a.components.length ? ` · ${a.components.length} composants` : ""}</Text> },
  { accessor: "acquisition_cents", title: "Valeur d'origine", textAlign: "right", render: (a) => <MoneyText cents={a.acquisition_cents} /> },
  { accessor: "accumulated_cents", title: "Amortissements", textAlign: "right", render: (a) => <MoneyText cents={a.accumulated_cents} /> },
  { accessor: "net_cents", title: "Valeur nette", textAlign: "right", render: (a) => <MoneyText cents={a.net_cents} /> },
  { accessor: "status", title: "État", render: (a) => <StatusBadge tone={STATUS_TONES[a.status] ?? "neutral"}>{a.status_label}</StatusBadge> },
];

export default function AssetsPage() {
  const [params, setParams] = useUrlParams({ status: "", living: "" });
  const query = new URLSearchParams({ ...(params.status ? { status: params.status } : {}), ...(params.living ? { living: "1" } : {}) }).toString();
  const { data, isFetching } = useList<AssetItem, AssetsMeta>(ASSETS_KEY, `/api/v1/assets${query ? `?${query}` : ""}`);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<AssetDraft | undefined>();
  const can = useCan();
  const goTo = useGoTo();
  const close = () => { setCreating(false); setDraft(undefined); };
  return (
    <>
      <PageHeader title="Immobilisations" description="Registre des immobilisations : plan d'amortissement par fiche (linéaire ou dégressif, année de 360 jours), dotations passées à la clôture."
        actions={<><CalculatorLink code="amortissement" label="Simuler un amortissement" /><CalculatorLink code="cout-materiel" label="Coût d'un matériel" />
          <Can><Button onClick={() => setCreating(true)}>Nouvelle immobilisation</Button></Can></>} />
      {data?.meta && !data.meta.enabled && <Alert color="ardoise" variant="light" mb="sm">Registre seulement : les amortissements ne sont pas
        comptabilisés pour cette structure (réglage à valider avec l'expert-comptable).</Alert>}
      <FilterBar>
        <Select label="État" placeholder="Tous" clearable data={data?.meta?.statuses ?? []} w={180}
          value={params.status || null} onChange={(v) => setParams({ status: v ?? "" })} />
        {data?.meta?.living_kinds && data.items.some((a) => a.living) || params.living ? (
          <Checkbox label="Biens vivants" checked={!!params.living} onChange={(e) => setParams({ living: e.currentTarget.checked ? "1" : "" })} />) : null}
      </FilterBar>
      <LedgerGapsCard canWrite={can.write} onCreate={(d) => { setDraft(d); setCreating(true); }} />
      <DataGrid id="assets" records={data?.items} columns={COLUMNS} fetching={isFetching} emptyText="Aucune immobilisation." />
      {params.living && <ReinvestmentsPanel />}
      <FormModal opened={creating} onClose={close} title={draft ? "Fiche de reprise" : "Nouvelle immobilisation"} size="xl">
        {creating && data?.meta && <AssetForm asset={null} meta={data.meta} draft={draft} onDone={(item) => { close(); if (item) goTo(`/assets/${item.id}`); }} />}
      </FormModal>
    </>
  );
}
