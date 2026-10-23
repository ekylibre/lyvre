// Associés : parts détenues par nature (pleine propriété, usufruit, nue-propriété) et % du
// capital à une date, solde du compte courant (sous-compte 455). Création par l'administrateur.
import { Button, Group, Text, TextInput } from "@mantine/core";
import { useList } from "../../api/resources";
import { useCan } from "../../api/session";
import { AppLink } from "../../app/navigation";
import { useRouteModal } from "../../app/useRouteModal";
import { DataGrid, type GridColumn } from "../../components/DataGrid";
import { FilterBar, useUrlParams } from "../../components/FilterBar";
import { FormModal } from "../../components/FormModal";
import { MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AssociateForm } from "./AssociateForm";
import { ASSOCIATES_KEY, balanceLabel, NATURES, type Associate, type AssociatesMeta } from "./types";

const percent = (value: number) => `${value.toLocaleString("fr-FR", { maximumFractionDigits: 2 })} %`;

export function BalanceCell({ cents }: { cents: number }) {
  return (
    <div style={{ textAlign: "right" }}>
      <MoneyText cents={Math.abs(cents)} size="sm" anomaly={cents < 0} />
      <Text size="xs" c="dimmed">{balanceLabel(cents)}</Text>
    </div>
  );
}

export default function AssociatesPage() {
  const can = useCan();
  const modal = useRouteModal("/associates/");
  const [params, setParams] = useUrlParams({ at: "" });
  const url = `/api/v1/associates${params.at ? `?at=${params.at}` : ""}`;
  const { data, isFetching } = useList<Associate, AssociatesMeta>(ASSOCIATES_KEY, url);
  const meta = data?.meta;

  const columns: GridColumn<Associate>[] = [
    { accessor: "name", title: "Associé", sortable: true, hideable: false, render: (a) => (
      <Group gap="xs"><AppLink href={`/associates/${a.id}`}>{a.name}</AppLink>
        {a.is_out && <StatusBadge tone="neutral">Sans parts</StatusBadge>}</Group>
    ) },
    { accessor: "account_code", title: "Compte courant", render: (a) => <span className="lv-num">{a.account_code}</span> },
    ...NATURES.map((n): GridColumn<Associate> => ({
      accessor: n.value, title: n.short, textAlign: "right",
      render: (a) => a.parts[n.value]
        ? <div><span className="lv-num">{a.parts[n.value].toLocaleString("fr-FR")}</span>
            <Text size="xs" c="dimmed">{percent(a.percent[n.value])}</Text></div>
        : <Text c="dimmed" size="sm">—</Text>,
    })),
    { accessor: "balance_cents", title: "Solde du compte courant", textAlign: "right", sortable: true,
      render: (a) => <BalanceCell cents={a.balance_cents} /> },
  ];

  return (
    <>
      <PageHeader title="Associés" description="Parts détenues et comptes courants des associés."
        actions={can.instanceAdmin && <Button onClick={modal.openNew}>Nouvel associé</Button>} />
      <FilterBar>
        <TextInput type="date" label="Situation au" value={params.at} onChange={(e) => setParams({ at: e.currentTarget.value })} />
        {meta && (
          <Text size="sm" c="dimmed">
            {meta.total_parts.toLocaleString("fr-FR")} parts au {formatDate(meta.at)} · comptes courants :{" "}
            <MoneyText cents={meta.balances_total_cents} size="sm" />
          </Text>
        )}
      </FilterBar>
      <DataGrid id="associates" records={data?.items} columns={columns} fetching={isFetching}
        defaultSort={{ column: "name", direction: "asc" }}
        emptyText="Aucun associé. Ajoutez les associés de la société : chacun reçoit un compte courant 4551…" />
      <FormModal opened={modal.mode === "new" && can.instanceAdmin} onClose={modal.close} title="Nouvel associé">
        <AssociateForm key={meta ? "ready" : "loading"} associate={null} meta={meta} onDone={modal.close} />
      </FormModal>
    </>
  );
}
