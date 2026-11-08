// Tableau de bord : « À traiter » (lot DB1). Une seule liste pour ce qui demande une action — trésorerie négative
// prévue, factures échues, écritures en brouillard anciennes, intégrations recommandées — au lieu de bandeaux
// empilés : filet de gravité (brique, paille, lichen), pastille d'icône, une phrase, une action.
import type { ReactNode } from "react";
import { Anchor, Button, Group, Paper, Stack, Text, Title } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useAction, type Notice } from "../../api/resources";
import { SESSION_KEY, useCurrentSession } from "../../api/session";
import { AppLink } from "../../app/navigation";
import { IconTile } from "../../components/IconTile";
import { MoneyText } from "../../components/Money";
import { useForecast } from "../cash-forecast/CashForecastPage";
import { INTEGRATION_PITCHES, integrationLabel } from "../integrations/catalog";
import { IntegrationLogo } from "../integrations/IntegrationLogo";

export interface Signal { key: string; tone: "brique" | "paille" | "lichen" | "ardoise"; icon: ReactNode; title: ReactNode; detail?: ReactNode; action: ReactNode }

export function SignalRow({ signal }: { signal: Signal }) {
  return (
    <div className="lv-signal" data-tone={signal.tone} role="listitem">
      {signal.icon}
      <div><Text size="sm" fw={500}>{signal.title}</Text>{signal.detail && <Text size="xs" c="dimmed">{signal.detail}</Text>}</div>
      <div>{signal.action}</div>
    </div>
  );
}

export interface AgentCounts { purchases: number; entities: number; entries: number; total: number }

/** Lot AK3 : saisies par clé d'API (Aiffel…) à vérifier ; lien vers la liste la plus utile. */
export function agentSignalHref(agent: AgentCounts): string {
  if (agent.purchases) return "/purchases/?from_key=1";
  if (agent.entries) return "/entries/?state=draft";
  return "/entities/";
}

export function AttentionCard({ drafts, overdue, agent }: {
  drafts: number; overdue: { count: number; cents: number } | null; agent?: AgentCounts | null;
}) {
  const { data: forecast } = useForecast();
  const proposed = useCurrentSession().instance?.integrations?.proposed ?? [];
  const client = useQueryClient();
  const dismiss = useAction((slug: string) => api.post<{ notices: Notice[] }>(`/api/v1/integrations/${slug}/dismiss`));
  const signals: Signal[] = [];
  const negative = forecast?.first_negative;
  if (negative) {
    const month = forecast.months.find((m) => m.month === negative.month)?.label ?? "";
    signals.push({ key: "forecast", tone: "brique", icon: <IconTile icon="trending-up" size={32} color="brique" />,
      title: "Trésorerie négative prévue", detail: <>Solde prévu de <MoneyText cents={negative.closing_cents} anomaly size="xs" /> fin {month}</>,
      action: <Anchor component={AppLink} href="/treasury/forecast" size="sm">Voir le prévisionnel</Anchor> });
  }
  if (overdue?.count) {
    signals.push({ key: "overdue", tone: "brique", icon: <IconTile icon="file-clock" size={32} color="brique" />,
      title: `${overdue.count} facture(s) échue(s) à relancer`, detail: <><MoneyText cents={overdue.cents} size="xs" /> restant dû</>,
      action: <Anchor component={AppLink} href="/sales/?overdue=1" size="sm">Relancer</Anchor> });
  }
  if (agent?.total) {
    const parts = [agent.purchases && `${agent.purchases} facture(s) d'achat`, agent.entities && `${agent.entities} tiers`,
      agent.entries && `${agent.entries} écriture(s)`].filter(Boolean).join(", ");
    signals.push({ key: "agent", tone: "paille", icon: <IconTile icon="bot" size={32} color="paille" />,
      title: `${agent.total} saisie(s) par clé d'API à vérifier`, detail: parts,
      action: <Anchor component={AppLink} href={agentSignalHref(agent)} size="sm">Vérifier</Anchor> });
  }
  if (drafts) {
    signals.push({ key: "drafts", tone: "paille", icon: <IconTile icon="notebook-pen" size={32} color="paille" />,
      title: `${drafts} écriture(s) en brouillard depuis plus de 3 mois`, detail: "À valider une fois vérifiées",
      action: <Anchor component={AppLink} href="/entries/?state=draft" size="sm">Valider</Anchor> });
  }
  for (const slug of proposed) {
    signals.push({ key: `integration-${slug}`, tone: "lichen", icon: <IntegrationLogo slug={slug} size={32} />,
      title: `Activer ${integrationLabel(slug)}`, detail: INTEGRATION_PITCHES[slug] ?? "Intégration recommandée pour votre structure.",
      action: <Group gap={4} wrap="nowrap">
        <Button size="compact-sm" component={AppLink} href={`/configuration/integrations/${slug}`}>Configurer</Button>
        <Button size="compact-sm" variant="subtle" loading={dismiss.isPending && dismiss.variables === slug}
          onClick={() => dismiss.mutate(slug, { onSuccess: () => void client.invalidateQueries({ queryKey: SESSION_KEY }) })}>
          Ne plus proposer</Button></Group> });
  }
  return (
    <Paper p="md" h="100%">
      <Group gap="xs" mb="sm" wrap="nowrap"><IconTile icon="list-checks" size={28} /><Title order={2} size="h3">À traiter</Title></Group>
      {signals.length ? <Stack gap={8} role="list" aria-label="À traiter">{signals.map((s) => <SignalRow key={s.key} signal={s} />)}</Stack>
        : <Text size="sm" c="dimmed">Rien en attente : la comptabilité est à jour.</Text>}
    </Paper>
  );
}
