// Contrôles et téléchargement du FEC d'un exercice (GET /api/v1/fiscal-years/<id>/fec/check) :
// erreurs bloquantes, avertissements, relecture du fichier, totaux, lien de téléchargement.
// Réutilisé par l'assistant de clôture.
import { Alert, Anchor, Button, Center, Group, List, Loader, SimpleGrid, Stack, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { api } from "../../api/client";
import { MoneyText } from "../../components/Money";
import { AppLink } from "../../app/navigation";

export interface FecCheck {
  errors: string[]; warnings: string[]; problems: string[]; filename: string | null; frozen: boolean;
  sha256: string | null; download_url: string | null;
  stats: { lines: number; entries: number; total_debit_cents: number; total_credit_cents: number } | null;
}

export function FecPanel({ fiscalYearId }: { fiscalYearId: number }) {
  const { data, isFetching } = useQuery({ queryKey: ["fec-check", fiscalYearId], staleTime: 0,
    queryFn: () => api.get<FecCheck>(`/api/v1/fiscal-years/${fiscalYearId}/fec/check`) });
  if (!data) return <Center h={120}><Loader /></Center>;
  const sirenMissing = data.errors.some((e) => e.includes("SIREN"));
  return (
    <Stack>
      {data.errors.length > 0 && (
        <Alert color="brique" title="Le FEC ne peut pas encore être produit">
          <List size="sm">{data.errors.map((e) => <List.Item key={e}>{e}</List.Item>)}</List>
          {sirenMissing && <Anchor component={AppLink} href="/configuration/organization" size="sm">Renseigner le SIREN</Anchor>}
        </Alert>
      )}
      {data.warnings.length > 0 && (
        <Alert color="paille" title="À vérifier"><List size="sm">{data.warnings.map((w) => <List.Item key={w}>{w}</List.Item>)}</List></Alert>
      )}
      {data.problems.length > 0 && (
        <Alert color="brique" title="Anomalies dans le fichier produit"><List size="sm">{data.problems.map((p) => <List.Item key={p}>{p}</List.Item>)}</List></Alert>
      )}
      {data.stats && (
        <>
          <SimpleGrid cols={{ base: 2, sm: 4 }}>
            <Stat label="Écritures" value={String(data.stats.entries)} />
            <Stat label="Lignes" value={String(data.stats.lines)} />
            <Stat label="Total débit" value={<MoneyText cents={data.stats.total_debit_cents} />} />
            <Stat label="Total crédit" value={<MoneyText cents={data.stats.total_credit_cents} />} />
          </SimpleGrid>
          {data.problems.length === 0 && <Text size="sm" c="var(--lv-lichen)">✓ Format relu : 18 champs, écritures équilibrées, numérotation continue par journal.</Text>}
          <Text size="xs" c="dimmed">
            {data.frozen ? "Fichier figé à la clôture définitive" : "Fichier produit à la demande"} · empreinte SHA-256{" "}
            <Text span className="lv-num" size="xs">{data.sha256?.slice(0, 16)}…</Text>. Contrôle officiel : outil « Test Compta Demat » de la DGFiP.
          </Text>
          <Group>
            <Button component="a" href={data.download_url ?? undefined} leftSection={<Download size={16} />} loading={isFetching}>
              Télécharger {data.filename}
            </Button>
          </Group>
        </>
      )}
    </Stack>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return <div><Text size="xs" c="dimmed">{label}</Text><Text fw={600} className="lv-num">{value}</Text></div>;
}
