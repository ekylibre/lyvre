// Indicateurs › Rapport d'activité : aperçu du rapport (HTML produit par le serveur, sans script),
// mode éco, PDF et exports (HTML, DOCX, ODT) ; accès aux textes, tonnages, photos et archives.
import { Alert, Button, Center, Group, Loader, Switch } from "@mantine/core";
import { useCan } from "../../api/session";
import { FilterBar } from "../../components/FilterBar";
import { PageHeader } from "../../components/PageHeader";
import { AppLink } from "../../app/navigation";
import { FiscalYearSelect, useReportContext, withFy } from "./shared";

export default function ReportPage() {
  const { setParams, context } = useReportContext();
  const data = context.data;
  const fyId = data?.fiscal_year.id;
  const admin = useCan().instanceAdmin;
  if (context.error) return <><PageHeader title="Rapport d'activité" /><Alert color="ardoise">{(context.error as Error).message}</Alert></>;
  return (
    <>
      <PageHeader title="Rapport d'activité" description={data ? `Exercice ${data.fiscal_year.label}` : undefined}
        actions={<>
          {admin && <Button variant="default" component={AppLink} href={withFy("/rapport-activite/edit", fyId)}>Éditer les textes</Button>}
          {admin && <Button variant="default" component={AppLink} href="/rapport-activite/eco">Tonnages éco</Button>}
          {admin && <Button variant="default" component={AppLink} href={withFy("/rapport-activite/photos", fyId)}>Photos</Button>}
          <Button variant="default" component={AppLink} href={withFy("/rapport-activite/archives", fyId)}>Archives</Button>
        </>} />
      <FilterBar>
        <FiscalYearSelect context={data} onChange={(fy_id) => setParams({ fy_id })} />
        <Switch label="Éco au pro-rata" description="Trimestres à cheval sur l'exercice répartis au prorata (sinon indivisibles)"
          checked={data?.prorata ?? false} onChange={(e) => setParams({ prorata: e.currentTarget.checked ? "1" : "0" })} pb={4} />
        {data && (
          <Group gap="xs" pb={4}>
            <Button component="a" href={data.links.pdf} target="_blank" rel="noopener">PDF</Button>
            <Button variant="default" component="a" href={data.links.html}>HTML</Button>
            <Button variant="default" component="a" href={data.links.docx}>DOCX</Button>
            <Button variant="default" component="a" href={data.links.odt}>ODT</Button>
          </Group>
        )}
      </FilterBar>
      {data ? (
        // Aperçu en bac à sable : le HTML des textes (saisi par les administrateurs) ne peut rien exécuter.
        <iframe key={data.links.preview} src={data.links.preview} title="Aperçu du rapport" sandbox=""
          style={{ width: "100%", height: "80vh", border: "1px solid var(--lv-line)", borderRadius: 8, background: "#fff" }} />
      ) : <Center h={300}><Loader /></Center>}
    </>
  );
}
