// Fiche d'une immobilisation (lot F5) : plan, composants, tableau d'amortissement, mise en service
// d'une immobilisation en cours, sortie (cession ou mise au rebut), suppression.
import { useState } from "react";
import { useParams } from "react-router";
import { Anchor, Button, Center, Group, Loader, Paper, SegmentedControl, Select, SimpleGrid, Table, Text, TextInput, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { Can } from "../../components/Can";
import { ConfirmButton } from "../../components/ConfirmButton";
import { FormBody } from "../../components/ApiForm";
import { FormModal } from "../../components/FormModal";
import { MoneyInput, MoneyText } from "../../components/Money";
import { PageHeader } from "../../components/PageHeader";
import { StatusBadge } from "../../components/StatusBadge";
import { formatDate } from "../../lib/format";
import { AppLink, useGoTo } from "../../app/navigation";
import { AssetForm } from "./AssetForm";
import { ASSETS_KEY, STATUS_TONES, type AssetItem, type AssetsMeta } from "./types";

const today = () => new Date().toISOString().slice(0, 10);

const LIVING_KINDS = [{ value: "sale", label: "Cession" }, { value: "death", label: "Mort" }, { value: "casualty", label: "Sinistre" },
  { value: "sanitary_slaughter", label: "Abattage sanitaire" }, { value: "scrap", label: "Rebut" }];

/** Sortie d'un bien vivant (lot AG5.c) : cession, mort, sinistre, abattage sanitaire, rebut ; totale ou partielle. */
function LivingExitForm({ asset, onDone }: { asset: AssetItem; onDone: () => void }) {
  const [kind, setKind] = useState("sale");
  const [on, setOn] = useState(today());
  const [amount, setAmount] = useState<number | null>(null);
  const total = asset.living?.units ?? null;
  const [units, setUnits] = useState<string>(total != null ? String(total) : "");
  const indemnity = ["death", "casualty", "sanitary_slaughter"].includes(kind);
  const save = useAction(() => api.post<{ notices: Notice[] }>(`/api/v1/assets/${asset.id}/living-exits`, {
    date: on, kind, units: units === "" ? null : Number(units),
    ...(kind === "sale" ? { price_cents: amount ?? 0 } : indemnity ? { indemnity_cents: amount ?? 0 } : {}) }), { invalidate: [ASSETS_KEY] });
  return (
    <form onSubmit={(e) => { e.preventDefault(); save.mutate(undefined, { onSuccess: onDone }); }}>
      <FormBody submitLabel="Enregistrer la sortie" onCancel={onDone} loading={save.isPending}>
        <SegmentedControl value={kind} onChange={setKind} data={LIVING_KINDS} />
        <TextInput label="Date de sortie" type="date" required value={on} onChange={(e) => setOn(e.currentTarget.value)} />
        {total != null && <TextInput label={`Effectif sorti (sur ${total})`} inputMode="numeric" value={units}
          onChange={(e) => setUnits(e.currentTarget.value)}
          description="Moins que l'effectif : sortie partielle au coût moyen du lot (chaque composant scindé au prorata)." />}
        {(kind === "sale" || indemnity) && <MoneyInput label={kind === "sale" ? "Prix de cession" : "Indemnité (assurance, État)"}
          value={amount} onChange={setAmount} description={kind === "sale" ? "Sans facture de vente : 462 / 7571." : "Créance 462 / produit 7571."} />}
        <Text size="xs" c="dimmed">Dotation complémentaire jusqu'à la date, valeur nette en 6571 (résultat d'exploitation).
          {kind === "sanitary_slaughter" && " L'abattage sanitaire ouvre le registre de reconstitution du cheptel (2 ans)."}</Text>
      </FormBody>
    </form>
  );
}

function DisposeForm({ asset, onDone }: { asset: AssetItem; onDone: () => void }) {
  const [kind, setKind] = useState<"sold" | "scrapped">("sold");
  const [on, setOn] = useState(today());
  const [price, setPrice] = useState<number | null>(null);
  const total = asset.living?.units ?? null;
  const [units, setUnits] = useState<string>(total != null ? String(total) : "");
  const living = !!asset.living;
  const save = useAction(() => (living
    ? api.post<{ notices: Notice[] }>(`/api/v1/assets/${asset.id}/living-exit`, { date: on, kind, price_cents: price ?? 0,
      units: units === "" ? null : Number(units) })
    : api.post<{ notices: Notice[] }>(`/api/v1/assets/${asset.id}/dispose`, { date: on, kind, price_cents: price ?? 0 })),
  { invalidate: [ASSETS_KEY] });
  return (
    <form onSubmit={(e) => { e.preventDefault(); save.mutate(undefined, { onSuccess: onDone }); }}>
      <FormBody submitLabel="Enregistrer la sortie" onCancel={onDone} loading={save.isPending}>
        <SegmentedControl value={kind} onChange={(v) => setKind(v as "sold" | "scrapped")}
          data={[{ value: "sold", label: "Cession" }, { value: "scrapped", label: "Mise au rebut" }]} />
        <TextInput label="Date de sortie" type="date" required value={on} onChange={(e) => setOn(e.currentTarget.value)} />
        {living && total != null && <TextInput label={`Effectif sorti (sur ${total})`} inputMode="numeric" value={units}
          onChange={(e) => setUnits(e.currentTarget.value)}
          description="Moins que l'effectif : sortie partielle au coût moyen du lot (chaque composant scindé au prorata)." />}
        {kind === "sold" && <MoneyInput label="Prix de cession" value={price} onChange={setPrice}
          description="Sans facture de vente : créance 462 / produit 775." />}
        <Text size="xs" c="dimmed">{living ? "Bien vivant : dotation complémentaire, valeur nette en 6571, prix en 7571 (cession habituelle, résultat d'exploitation)."
          : "Dotation complémentaire jusqu'à la date, sortie de l'actif (valeur nette en 675)."}</Text>
      </FormBody>
    </form>
  );
}

function InServiceForm({ asset, meta, onDone }: { asset: AssetItem; meta: AssetsMeta; onDone: () => void }) {
  const [on, setOn] = useState(today());
  const [account, setAccount] = useState<string | null>(null);
  const save = useAction(() => api.post<{ notices: Notice[] }>(`/api/v1/assets/${asset.id}/in-service`, { date: on, account_id: Number(account) }),
    { invalidate: [ASSETS_KEY] });
  return (
    <form onSubmit={(e) => { e.preventDefault(); save.mutate(undefined, { onSuccess: onDone }); }}>
      <FormBody submitLabel="Mettre en service" onCancel={onDone} loading={save.isPending}>
        <TextInput label="Date de mise en service" type="date" required value={on} onChange={(e) => setOn(e.currentTarget.value)} />
        <Select label="Compte définitif" required searchable value={account} onChange={setAccount}
          data={meta.accounts.filter((a) => !a.label.startsWith("23"))} />
      </FormBody>
    </form>
  );
}

export default function AssetDetailPage() {
  const id = Number(useParams().asset_id);
  const goTo = useGoTo();
  const { data } = useQuery({ queryKey: [...ASSETS_KEY, id], queryFn: () => api.get<{ item: AssetItem; meta: AssetsMeta }>(`/api/v1/assets/${id}`) });
  const [modal, setModal] = useState<null | "edit" | "component" | "dispose" | "service">(null);
  const remove = useAction(() => api.delete<{ notices: Notice[] }>(`/api/v1/assets/${id}`), { invalidate: [ASSETS_KEY] });
  if (!data) return <Center h={300}><Loader /></Center>;
  const a = data.item;
  const out = a.status === "sold" || a.status === "scrapped";
  return (
    <>
      <PageHeader title={a.label}
        description={<Group component="span" gap={8}><StatusBadge tone={STATUS_TONES[a.status] ?? "neutral"}>{a.status_label}</StatusBadge>
          <span className="lv-num">{a.account.code}</span><span>{a.account.label}</span>
          {a.parent_id && <Anchor component={AppLink} href={`/assets/${a.parent_id}`} size="sm">bien parent</Anchor>}</Group>}
        actions={<>
          <Can>
            {!out && <Button variant="default" onClick={() => setModal("edit")}>Modifier</Button>}
            {a.status === "waiting" && <Button variant="default" onClick={() => setModal("service")}>Mettre en service</Button>}
            {!out && a.status !== "waiting" && <Button variant="default" onClick={() => setModal("dispose")}>Sortir de l'actif…</Button>}
            {!a.parent_id && !out && <Button variant="default" onClick={() => setModal("component")}>Ajouter un composant</Button>}
            {a.deletable && <ConfirmButton title={`Supprimer ${a.label} ?`} confirmLabel="Supprimer" loading={remove.isPending}
              onConfirm={() => remove.mutate(undefined, { onSuccess: () => goTo("/assets/") })}>Supprimer</ConfirmButton>}
          </Can>
          <Button variant="default" component={AppLink} href="/assets/">Immobilisations</Button>
        </>} />
      <SimpleGrid cols={{ base: 2, md: 4 }} mb="md">
        <Paper p="md"><Text size="sm" c="dimmed">Valeur d'origine</Text><MoneyText cents={a.acquisition_cents} fw={700} /></Paper>
        <Paper p="md"><Text size="sm" c="dimmed">Amortissements</Text><MoneyText cents={a.accumulated_cents} fw={700} /></Paper>
        <Paper p="md"><Text size="sm" c="dimmed">Valeur nette</Text><MoneyText cents={a.net_cents} fw={700} />
          {a.living?.units ? <Text size="xs" c="dimmed">{a.living.units} {a.living.species ?? ""} · <MoneyText cents={Math.round(a.net_cents / a.living.units)} /> par tête</Text> : null}</Paper>
        <Paper p="md"><Text size="sm" c="dimmed">Plan</Text><Text>{a.method_label}{a.duration_months ? ` · ${a.duration_months} mois` : ""}
          {a.fiscal_coefficient ? ` · coef. ${a.fiscal_coefficient.replace(".", ",")}` : ""}</Text>
          <Text size="xs" c="dimmed">{`Acquise le ${formatDate(a.acquired_on)}${a.in_service_date ? `, en service le ${formatDate(a.in_service_date)}` : ""}`}</Text></Paper>
      </SimpleGrid>
      {a.components.length > 0 && (
        <Paper p="md" mb="md">
          <Title order={3} size="h4" mb="xs">Composants</Title>
          <Table><Table.Tbody>{a.components.map((c) => (
            <Table.Tr key={c.id}><Table.Td><Anchor component={AppLink} href={`/assets/${c.id}`} size="sm">{c.label}</Anchor></Table.Td>
              <Table.Td className="lv-num">{c.account.code}</Table.Td><Table.Td>{c.method_label}{c.duration_months ? ` · ${c.duration_months} mois` : ""}</Table.Td>
              <Table.Td ta="right"><MoneyText cents={c.acquisition_cents} /></Table.Td><Table.Td ta="right"><MoneyText cents={c.net_cents} /></Table.Td></Table.Tr>
          ))}</Table.Tbody></Table>
        </Paper>
      )}
      {!!a.schedule?.length && (
        <Paper p="md">
          <Title order={3} size="h4" mb="xs">Tableau d'amortissement</Title>
          <Table>
            <Table.Thead><Table.Tr><Table.Th>Exercice</Table.Th><Table.Th>Période</Table.Th><Table.Th ta="right">Jours</Table.Th>
              <Table.Th ta="right">Dotation</Table.Th><Table.Th ta="right">Cumul</Table.Th><Table.Th ta="right">Valeur nette</Table.Th><Table.Th /></Table.Tr></Table.Thead>
            <Table.Tbody>{a.schedule.map((r) => (
              <Table.Tr key={r.start}><Table.Td>{r.label}</Table.Td>
                <Table.Td className="lv-num">{`${formatDate(r.start)} → ${formatDate(r.stop)}`}</Table.Td>
                <Table.Td ta="right" className="lv-num">{r.days}</Table.Td>
                <Table.Td ta="right"><MoneyText cents={r.amount_cents} /></Table.Td>
                <Table.Td ta="right"><MoneyText cents={r.cumulative_cents} /></Table.Td>
                <Table.Td ta="right"><MoneyText cents={r.net_cents} /></Table.Td>
                <Table.Td>{r.posted && <StatusBadge tone="ok">passée</StatusBadge>}</Table.Td></Table.Tr>
            ))}</Table.Tbody>
          </Table>
        </Paper>
      )}
      {a.notes && <Text size="sm" mt="md">{a.notes}</Text>}
      <FormModal opened={modal === "edit" || modal === "component"} onClose={() => setModal(null)}
        title={modal === "component" ? `Composant de ${a.label}` : `Modifier ${a.label}`} size="xl">
        {(modal === "edit" || modal === "component") && <AssetForm asset={modal === "edit" ? a : null} meta={data.meta}
          parentId={modal === "component" ? a.id : undefined} onDone={() => setModal(null)} />}
      </FormModal>
      <FormModal opened={modal === "dispose"} onClose={() => setModal(null)} title={`Sortie de ${a.label}`}>
        {modal === "dispose" && (a.living ? <LivingExitForm asset={a} onDone={() => setModal(null)} />
          : <DisposeForm asset={a} onDone={() => setModal(null)} />)}
      </FormModal>
      <FormModal opened={modal === "service"} onClose={() => setModal(null)} title={`Mise en service de ${a.label}`}>
        {modal === "service" && <InServiceForm asset={a} meta={data.meta} onDone={() => setModal(null)} />}
      </FormModal>
    </>
  );
}
