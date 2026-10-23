// À propos (page publique, sans connexion) : présentation de Lyvre, fonctionnalités par domaine,
// comparaison avec les logiciels cités par deux comparatifs (Pennylane, fiche pratique
// « meilleur logiciel comptabilité association », 27/04/2026 ; Independant.io, « logiciel
// comptabilité association »), limites actuelles et sources.
import type { ReactNode } from "react";
import {
  Anchor, Badge, Box, Button, Container, Group, Image, List, Paper, SimpleGrid, Stack, Table, Text, ThemeIcon, Title,
  useComputedColorScheme,
} from "@mantine/core";
import {
  BadgeCheck, Banknote, BarChart3, BookOpen, Building2, Calculator, FileCheck2, HandCoins, Landmark, Receipt, ShieldCheck,
  Users,
} from "lucide-react";
import symbol from "../../assets/lyvre-symbole.svg";
import symbolInverse from "../../assets/lyvre-symbole-inverse.svg";
import { Wordmark } from "../../app/AppShell/Wordmark";
import { useSession } from "../../api/session";

interface Domain { icon: ReactNode; title: string; items: string[] }

const DOMAINS: Domain[] = [
  { icon: <BookOpen size={18} />, title: "Comptabilité", items: [
    "Plan comptable associatif (règlement ANC 2018-06) ou SCI, choisi par structure",
    "Partie double : saisie au clavier, journaux, grand livre, balance, bilan et compte de résultat N / N-1",
    "Comptabilité simplifiée : recettes et dépenses par catégorie, sans débit ni crédit, passage en partie double sans ressaisie",
    "Contributions volontaires en nature (86 / 87), TVA par exercice",
  ] },
  { icon: <Landmark size={18} />, title: "Banque et caisse", items: [
    "Import OFX et synchronisation Qonto, dédoublonnage",
    "Rapprochement au clavier avec suggestions, en masse, annulable ; règles de catégorisation",
    "Caisse en espèces (53x), dépôts en banque par virement interne (581)",
    "Prévisionnel de trésorerie sur 12 mois avec alerte de solde négatif",
  ] },
  { icon: <Receipt size={18} />, title: "Achats", items: [
    "Factures fournisseurs Qonto ou déposées : lecture Factur-X, PDF ou photo (OCR)",
    "Catalogue de produits, comptabilisation en engagement (401 par fournisseur), règlements rapprochés",
  ] },
  { icon: <Users size={18} />, title: "Adhérents et tiers", items: [
    "Répertoire des tiers, adhésions HelloAsso et caisse, relances par email",
    "Bénévolat : temps de travaux et valorisation",
  ] },
  { icon: <HandCoins size={18} />, title: "Dons et reçus fiscaux", items: [
    "Dons repris de la comptabilité, donateur retrouvé par la banque ou le compte de tiers ; dons en nature",
    "Reçus particuliers (Cerfa 11580) et entreprises (Cerfa 16216), annuels ou par don, numérotation continue",
    "PDF figés, envoi par email, annulation motivée et réémission, état annuel",
  ] },
  { icon: <FileCheck2 size={18} />, title: "Clôture et obligations", items: [
    "Assistant de clôture en 8 étapes : contrôles, écritures d'inventaire, fonds dédiés, résultat, FEC",
    "Clôture provisoire puis définitive, réouverture motivée, à-nouveaux et extournes, affectation du résultat",
    "Fichier des écritures comptables (FEC) conforme à l'article A47 A-1 du LPF",
  ] },
  { icon: <Calculator size={18} />, title: "Budget et projets", items: [
    "Projets ou activités sur les écritures, les achats et les règles ; ventilation d'une ligne",
    "Budget annuel ou mensuel, copie de l'année précédente ; suivi prévu / réalisé / écart",
    "Compte de résultat d'un projet pour un financeur, exports tableur",
  ] },
  { icon: <BarChart3 size={18} />, title: "Pilotage et rapport d'AG", items: [
    "Tableau de bord : résultat, ventes, trésorerie, budget",
    "Indicateurs de visibilité et d'impact, rapport d'activité PDF / DOCX / ODT",
  ] },
  { icon: <ShieldCheck size={18} />, title: "Collaboration et souveraineté", items: [
    "Plusieurs structures dans une même installation, une base par structure",
    "Rôles par structure : administrateur, trésorier, expert-comptable en lecture seule",
    "Logiciel libre (AGPL-3.0), auto-hébergé, sauvegardes avec les pièces jointes",
  ] },
];

type Mark = "yes" | "partial" | "no" | null;
interface Row { label: string; marks: Mark[]; note?: string }

/** Colonnes : Lyvre puis les logiciels cités par les comparatifs. */
const PRODUCTS = ["Lyvre", "Pennylane", "AssoConnect", "macompta.fr", "Yapla", "Pep's Up", "Dolibarr", "B-Association", "AlauxSoft"];

// null : non mentionné par les comparatifs (ce qui ne veut pas dire absent du logiciel).
const ROWS: Row[] = [
  // Lyvre, Pennylane, AssoConnect, macompta.fr, Yapla, Pep's Up, Dolibarr, B-Association, AlauxSoft
  { label: "Plan comptable associatif", marks: ["yes", "yes", null, "yes", null, null, null, "yes", "yes"] },
  { label: "Partie double (bilan, compte de résultat)", marks: ["yes", "yes", "yes", "yes", "no", "no", null, "yes", null] },
  { label: "Comptabilité simplifiée (trésorerie)", marks: ["yes", null, "yes", null, "yes", "yes", null, null, null] },
  { label: "Import bancaire, rapprochement", marks: ["yes", "yes", null, null, null, null, null, null, "partial"],
    note: "AlauxSoft : suivi des comptes bancaires" },
  { label: "Caisse (espèces)", marks: ["yes", null, null, null, null, null, null, null, "yes"] },
  { label: "Factures fournisseurs, justificatifs", marks: ["yes", "yes", null, null, null, null, null, null, null] },
  { label: "Adhésions, cotisations, relances", marks: ["yes", "partial", "yes", null, "yes", null, "yes", "yes", null],
    note: "Pennylane : suivi des cotisations et dons" },
  { label: "Reçus fiscaux des dons", marks: ["yes", null, "yes", null, "yes", null, null, null, null] },
  { label: "Budget, suivi par projet", marks: ["yes", "yes", "yes", null, null, null, "partial", null, null],
    note: "Dolibarr : gestion de projets" },
  { label: "Prévisionnel de trésorerie", marks: ["yes", "yes", null, null, null, null, null, null, null] },
  { label: "Export FEC", marks: ["yes", null, null, null, null, null, null, null, "yes"] },
  { label: "Clôture guidée, affectation du résultat", marks: ["yes", null, null, null, null, null, null, null, null] },
  { label: "Fonds dédiés", marks: ["yes", null, null, null, null, null, null, null, null], note: "critère cité par Pennylane" },
  { label: "Rapport pour l'assemblée générale", marks: ["yes", null, null, null, null, null, null, null, null],
    note: "cité pour Ma Compta Association" },
  { label: "Plusieurs utilisateurs, rôles", marks: ["yes", null, null, "yes", null, null, "yes", null, null] },
  { label: "Plusieurs structures", marks: ["yes", null, null, null, null, null, null, null, "yes"] },
  { label: "Factures clients, devis", marks: ["partial", "yes", null, null, null, null, "yes", null, null], note: "Lyvre : via Odoo" },
  { label: "Remise de chèques, billetterie", marks: ["no", null, null, null, null, "yes", null, null, null] },
  { label: "Site web, CRM, communication", marks: ["no", null, "yes", null, null, null, null, null, null] },
  { label: "Application mobile", marks: ["partial", "yes", null, null, null, null, null, null, null],
    note: "Lyvre : interface lisible sur mobile" },
  { label: "Logiciel libre, auto-hébergeable", marks: ["yes", "no", "no", "no", "no", "no", "yes", null, null] },
  { label: "Gratuit", marks: ["yes", "no", "partial", "no", "partial", null, "yes", "yes", "partial"],
    note: "partiel : formule gratuite limitée" },
];

const LIMITS = [
  "Pas d'application mobile native : l'interface s'adapte au téléphone.",
  "Factures clients et devis seulement par l'intégration Odoo ; pas de remise de chèques ni de billetterie.",
  "Pas d'immobilisations ni d'amortissements calculés (comptes présents, sans suivi).",
  "Pas de paiement en ligne propre : les adhésions et dons en ligne passent par HelloAsso.",
  "Modèles de reçus fiscaux à faire relire face aux formulaires Cerfa en vigueur avant usage.",
];

function MarkCell({ mark, highlight }: { mark: Mark; highlight: boolean }) {
  const content = mark === "yes" ? <Text c="var(--lv-lichen)" fw={700} aria-label="oui">✓</Text>
    : mark === "partial" ? <Text c="var(--lv-paille-ink)" fw={600} fz={17} lh={1} aria-label="en partie">◐</Text>
      : mark === "no" ? <Text c="var(--lv-brique)" aria-label="non">✕</Text>
        : <Text c="dimmed" size="xs" aria-label="non mentionné">·</Text>;
  return <Table.Td ta="center" bg={highlight ? "var(--lv-sauge)" : undefined}>{content}</Table.Td>;
}

export default function AboutPage() {
  const dark = useComputedColorScheme("light") === "dark";
  const { data: session } = useSession();
  const signedIn = !!session?.user;
  return (
    <Box bg="var(--lv-paper)" mih="100vh">
      <Container size="lg" py="md">
        <Group justify="space-between">
          <Group gap="sm"><Image src={dark ? symbolInverse : symbol} w={36} h={36} alt="" /><Wordmark /></Group>
          <Button component="a" href={signedIn ? "/" : "/login"}>{signedIn ? "Ouvrir l'application" : "Se connecter"}</Button>
        </Group>

        <Stack gap="xs" mt={48} mb={40} maw={760}>
          <Badge variant="light" color="lichen" w="fit-content">Logiciel libre · AGPL-3.0 · auto-hébergé</Badge>
          <Title order={1} fz={{ base: 32, sm: 42 }} lh={1.15}>La comptabilité des associations, libre, sobre et souveraine.</Title>
          <Text size="lg" c="dimmed">
            Lyvre tient la comptabilité d'une association ou d'une SCI, de la saisie au bilan : banque et caisse,
            achats, adhésions, dons et reçus fiscaux, budget et projets, clôture et FEC pour l'expert-comptable.
            En partie double, ou simplifiée pour les petites structures.
          </Text>
        </Stack>

        <Title order={2} mb="md">Fonctionnalités</Title>
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} mb={48}>
          {DOMAINS.map((d) => (
            <Paper key={d.title} p="md">
              <Group gap="xs" mb="xs"><ThemeIcon variant="light" color="lichen" radius="md">{d.icon}</ThemeIcon><Title order={3} size="h4">{d.title}</Title></Group>
              <List size="sm" spacing={4}>{d.items.map((item) => <List.Item key={item}>{item}</List.Item>)}</List>
            </Paper>
          ))}
        </SimpleGrid>

        <Title order={2} mb={4}>Lyvre et les autres logiciels</Title>
        <Text size="sm" c="dimmed" mb="md" maw={820}>
          Logiciels et fonctionnalités tels que présentés par deux comparatifs publics. Un point « · » signifie que le
          comparatif ne mentionne pas la fonctionnalité, pas qu'elle est absente du logiciel ; les offres évoluent :
          vérifiez auprès de chaque éditeur.
        </Text>
        <Paper p={0} mb="xs" style={{ overflowX: "auto" }}>
          <Table verticalSpacing={6} miw={900} stickyHeader>
            <Table.Thead bg="var(--lv-surface)">
              <Table.Tr>
                <Table.Th />
                {PRODUCTS.map((p, i) => <Table.Th key={p} ta="center" bg={i === 0 ? "var(--lv-sauge)" : undefined}>{p}</Table.Th>)}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {ROWS.map((row) => (
                <Table.Tr key={row.label}>
                  <Table.Td><Text size="sm">{row.label}</Text>{row.note && <Text size="xs" c="dimmed">{row.note}</Text>}</Table.Td>
                  {row.marks.map((mark, i) => <MarkCell key={PRODUCTS[i]} mark={mark} highlight={i === 0} />)}
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Paper>
        <Text size="xs" c="dimmed" mb={48}>✓ oui · ◐ en partie ou formule limitée · ✕ non · « · » non mentionné. Aussi cités :
          MaCotisation (cotisations, logiciel comptable intégré), Ma Compta Association (catégories, rapport d'AG,
          installation locale), Sage 50 (comptabilité d'engagement, stocks).</Text>

        <SimpleGrid cols={{ base: 1, md: 2 }} mb={48}>
          <Paper p="md">
            <Group gap="xs" mb="xs"><ThemeIcon variant="light" color="lichen" radius="md"><BadgeCheck size={18} /></ThemeIcon>
              <Title order={3} size="h4">Ce qui distingue Lyvre</Title></Group>
            <List size="sm" spacing={4}>
              <List.Item>Libre et auto-hébergé : vos données restent chez vous, sans abonnement.</List.Item>
              <List.Item>Clôture complète guidée et FEC, comme un logiciel d'expert-comptable.</List.Item>
              <List.Item>Rapprochement bancaire au clavier, lecture des factures, règles automatiques.</List.Item>
              <List.Item>Plusieurs structures et rôles par structure, dont l'expert-comptable en lecture seule.</List.Item>
              <List.Item>Partie double ou simplifiée, avec passage de l'une à l'autre sans ressaisie.</List.Item>
            </List>
          </Paper>
          <Paper p="md">
            <Group gap="xs" mb="xs"><ThemeIcon variant="light" color="paille" radius="md"><Building2 size={18} /></ThemeIcon>
              <Title order={3} size="h4">Ce que Lyvre ne fait pas (encore)</Title></Group>
            <List size="sm" spacing={4}>{LIMITS.map((l) => <List.Item key={l}>{l}</List.Item>)}</List>
          </Paper>
        </SimpleGrid>

        <Group gap="xs" mb={4}><Banknote size={16} /><Text size="sm" fw={600}>Sources de la comparaison</Text></Group>
        <List size="xs" c="dimmed" mb={40}>
          <List.Item><Anchor href="https://www.pennylane.com/fr/fiches-pratiques/comptabilite/meilleur-logiciel-comptabilite-association"
            target="_blank" rel="noreferrer" size="xs">Pennylane, « Meilleur logiciel de comptabilité pour association » (27/04/2026)</Anchor>
            {" "}— comparatif publié par un éditeur présent dans la liste.</List.Item>
          <List.Item><Anchor href="https://lp.independant.io/logiciel-comptabilite/association/" target="_blank" rel="noreferrer" size="xs">
            Independant.io, « Logiciel comptabilité association »</Anchor></List.Item>
        </List>
        <Text size="xs" c="dimmed" ta="center" pb="lg">LOGICIEL LIBRE · AGPL-3.0 · AUTO-HÉBERGÉ</Text>
      </Container>
    </Box>
  );
}
