// À propos (page publique, sans connexion) : présentation de Lyvre, fonctionnalités par domaine,
// comparaison avec les logiciels cités par deux comparatifs (Pennylane, Independant.io), vérifiée sur
// les sites des éditeurs (competitors.ts), comparaison avec les logiciels open source (openSourceVendors.ts),
// limites actuelles et sources.
import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Anchor, Badge, Box, Button, Container, Group, Image, List, Paper, SimpleGrid, Stack, Table, Text, ThemeIcon, Title, Tooltip,
  useComputedColorScheme,
} from "@mantine/core";
import {
  BadgeCheck, Banknote, BarChart3, BookOpen, Briefcase, Building2, Calculator, FileCheck2, FileText, HandCoins, Home, Landmark,
  Receipt, ShieldCheck, Sprout, Users,
} from "lucide-react";
import symbol from "../../assets/lyvre-symbole.svg";
import symbolInverse from "../../assets/lyvre-symbole-inverse.svg";
import { Wordmark } from "../../app/AppShell/Wordmark";
import { api } from "../../api/client";
import { useSession } from "../../api/session";
import { CHECKED_ON, type Evidence, type Mark, type Vendor, VENDORS } from "./competitors";
import { OSS_VENDORS } from "./openSourceVendors";

interface Domain { icon: ReactNode; title: string; items: string[] }

const DOMAINS: Domain[] = [
  { icon: <BookOpen size={18} />, title: "Comptabilité", items: [
    "Plan comptable associatif (règlement ANC 2018-06), agricole, SCI ou société (PCG 2026, bilan et résultat de la liasse 2050), choisi par structure",
    "Partie double : saisie au clavier, journaux, grand livre, balance, bilan et compte de résultat N / N-1",
    "Comptabilité simplifiée : recettes et dépenses par catégorie, sans débit ni crédit, passage en partie double sans ressaisie",
    "Écritures validées par lots, intangibles ensuite (extourne pour corriger), historique ; verrouillage de période",
    "Lettrage automatique ou au clavier des comptes de tiers, à-nouveaux détaillés",
    "Immobilisations : composants, plans linéaire et dégressif, dotations à la clôture, cession ; charges et produits constatés d'avance",
    "Contributions volontaires en nature (86 / 87), TVA par exercice",
    "TVA codée sur les écritures et déclaration CA3 mensuelle préparée (autoliquidation, importations, avoirs), PDF et tableur pour TeleDEC",
    "Éditions réunies : bilan, compte de résultat, soldes intermédiaires de gestion, balance, grand livre, journaux",
  ] },
  { icon: <Landmark size={18} />, title: "Banque et caisse", items: [
    "Import OFX et synchronisation Qonto, dédoublonnage",
    "Rapprochement au clavier avec suggestions, en masse, annulable ; règles de catégorisation",
    "Transactions classées par feux (à jour, à traiter, anomalie), catégories Qonto, factures de vente encaissées depuis le relevé",
    "Relevés de compte PDF récupérés de Qonto ou déposés, archive de l'exercice pour l'expert-comptable (FEC et relevés)",
    "Caisse en espèces (53x), dépôts en banque par virement interne (581)",
    "Prévisionnel de trésorerie sur 12 mois avec alerte de solde négatif",
  ] },
  { icon: <Receipt size={18} />, title: "Achats", items: [
    "Factures fournisseurs Qonto ou déposées : lecture Factur-X, PDF ou photo (OCR) ; fournisseur trouvé dans Sirene",
    "Catalogue de produits, comptabilisation en engagement (401 par fournisseur), règlements rapprochés",
    "Abonnements (internet, téléphone, assurance, banque) : échéances attendues, facture et prélèvement rattachés, préavis",
  ] },
  { icon: <FileText size={18} />, title: "Ventes", items: [
    "Devis, factures et avoirs numérotés, PDF Factur-X, écriture au journal des ventes, envoi par email",
    "Encaissements rapprochés de la banque, TVA à l'encaissement ou sur les débits, relances",
    "Factures récurrentes, avis d'échéance et quittances",
    "Facture électronique : émission et réception par une plateforme agréée, SuperPDP ou Qonto (une seule à la fois, comme le veut la réforme)",
  ] },
  { icon: <Sprout size={18} />, title: "Exploitation agricole", items: [
    "Plan agricole, micro-BA, réel simplifié ou normal ; TVA agricole (RFA, acomptes, CA12A, CA3 trimestrielle)",
    "Échéancier fiscal, social (MSA) et PAC avec résumé du lundi par email et calendrier iCal",
    "Aides PAC et subventions, inventaire et stocks, avances aux cultures, biens vivants, ICHN",
    "Activités et campagnes : surfaces, marges par activité, ventilation analytique",
    "Résultat fiscal, DEP, aide à la liasse et assiette MSA ; e-reporting des ventes aux particuliers",
    "Calculettes agricoles et assistant (Claude) qui répond sur le dossier et prépare des brouillons à valider",
    "Lecture d'Ekylibre : activités, surfaces, coûts des interventions et quantités en stock",
  ] },
  { icon: <Briefcase size={18} />, title: "Entreprise de services", items: [
    "SAS, SASU, SARL : capital, associés et comptes courants, exercice décalé",
    "Bilan et compte de résultat de la liasse 2050, CA3 avec contrôles et verrou, exports pour TeleDEC",
    "Ventes et achats en engagement, encours clients, relances, rapprochement avec Qonto",
  ] },
  { icon: <Home size={18} />, title: "SCI et baux", items: [
    "Associés : registre des parts, comptes courants, notes de frais, gérants",
    "Baux par lots (bâtiments, terres), modèles relus et texte figé, carte des parcelles et bâtiments (IGN)",
    "Signature électronique des baux (Documenso auto-hébergé), paraphe sur chaque page",
    "Révision des loyers : indices INSEE (ILC, ILAT, IRL) lus automatiquement, indice des fermages, courrier au locataire",
  ] },
  { icon: <Users size={18} />, title: "Adhérents et tiers", items: [
    "Répertoire des tiers, pré-rempli et mis à jour depuis l'API Sirene de l'INSEE (SIREN, adresse, NAF, TVA)",
    "Adhésions HelloAsso et caisse, relances par email, bénévolat : temps de travaux et valorisation",
    "Liste des adhérents synchronisée vers Brevo, sans doublon et sans réinscrire les désinscrits",
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
    "Reprise d'historique depuis un FEC, un export Isacompta ou un tableur",
    "Restauration d'une sauvegarde Ekylibre en une fois : écritures et à-nouveaux, tiers, banque, achats et ventes, pièces, activités et dernier inventaire, avec rapport de contrôle",
  ] },
  { icon: <Calculator size={18} />, title: "Budget et projets", items: [
    "Projets ou activités sur les écritures, les achats et les règles ; ventilation d'une ligne",
    "Budget annuel ou mensuel, copie de l'année précédente ; suivi prévu / réalisé / écart",
    "Compte de résultat d'un projet pour un financeur, exports tableur",
  ] },
  { icon: <BarChart3 size={18} />, title: "Pilotage et rapport d'AG", items: [
    "Tableau de bord : ce qui est à traiter, échéancier de la semaine, résultat, facturé et encours clients, trésorerie, budget",
    "Documents : toutes les pièces (factures, relevés, baux, reçus) consultables au même endroit",
    "Indicateurs de visibilité et d'impact, rapport d'activité PDF / DOCX / ODT",
  ] },
  { icon: <ShieldCheck size={18} />, title: "Collaboration et souveraineté", items: [
    "Plusieurs structures dans une même installation, une base par structure ; écrans adaptés à l'association, à la SCI, à l'exploitation ou à la société",
    "Rôles par structure : administrateur, trésorier, expert-comptable en lecture seule ; mot de passe oublié par email",
    "Logiciel libre (AGPL-3.0), auto-hébergé, sauvegardes avec les pièces jointes",
  ] },
];

interface Row { key: string; label: string; lyvre: Mark; note?: string }

/** Une ligne par critère ; la colonne Lyvre ici, les autres dans competitors.ts. */
const ROWS: Row[] = [
  { key: "plan_asso", label: "Plan comptable associatif", lyvre: "yes" },
  { key: "double_entry", label: "Partie double (bilan, compte de résultat)", lyvre: "yes" },
  { key: "simple_mode", label: "Comptabilité simplifiée (trésorerie)", lyvre: "yes" },
  { key: "bank_import", label: "Import bancaire, rapprochement", lyvre: "yes" },
  { key: "cash", label: "Caisse (espèces)", lyvre: "yes" },
  { key: "supplier_invoices", label: "Factures fournisseurs, justificatifs", lyvre: "yes" },
  { key: "members", label: "Adhésions, cotisations, relances", lyvre: "yes" },
  { key: "tax_receipts", label: "Reçus fiscaux des dons", lyvre: "yes" },
  { key: "budget_projects", label: "Budget, suivi par projet", lyvre: "yes" },
  { key: "cash_forecast", label: "Prévisionnel de trésorerie", lyvre: "yes" },
  { key: "fec", label: "Export FEC", lyvre: "yes" },
  { key: "closing", label: "Clôture guidée, affectation du résultat", lyvre: "yes" },
  { key: "dedicated_funds", label: "Fonds dédiés", lyvre: "yes" },
  { key: "ag_report", label: "Rapport pour l'assemblée générale", lyvre: "yes" },
  { key: "multi_users", label: "Plusieurs utilisateurs, rôles", lyvre: "yes" },
  { key: "multi_entities", label: "Plusieurs structures", lyvre: "yes" },
  { key: "sales_invoices", label: "Factures clients, devis", lyvre: "yes" },
  { key: "cheques_ticketing", label: "Remise de chèques, billetterie", lyvre: "no" },
  { key: "website_crm", label: "Site web, CRM, communication", lyvre: "no" },
  { key: "mobile_app", label: "Application mobile", lyvre: "partial", note: "Lyvre : interface lisible sur mobile" },
  { key: "free_software", label: "Logiciel libre, auto-hébergeable", lyvre: "yes" },
  { key: "free_tier", label: "Gratuit", lyvre: "yes" },
];

/** Critères ajoutés pour les logiciels open source, documentés chez eux (pas chez les éditeurs du premier tableau). */
const OSS_ROWS: Row[] = [
  ...ROWS,
  { key: "sci", label: "SCI : associés, baux, quittances", lyvre: "yes" },
  { key: "lettering", label: "Lettrage des comptes de tiers", lyvre: "yes" },
  { key: "entry_lock", label: "Écritures validées intangibles", lyvre: "yes" },
  { key: "fixed_assets", label: "Immobilisations, amortissements", lyvre: "yes" },
  { key: "vat_return", label: "Déclaration de TVA préparée", lyvre: "yes", note: "Lyvre : CA3 mensuelle, saisie sur TeleDEC" },
  { key: "einvoicing", label: "Facture électronique, plateforme agréée", lyvre: "yes", note: "Lyvre : Factur-X émis et lu, SuperPDP ou Qonto" },
  { key: "sepa_online", label: "Prélèvement SEPA, paiement en ligne", lyvre: "no" },
];

const LIMITS = [
  "Pas d'application mobile native : l'interface s'adapte au téléphone.",
  "Pas de remise de chèques ni de billetterie ; la facture électronique (réforme 2026-2027) passe par une plateforme agréée, SuperPDP ou Qonto.",
  "Déclaration de TVA préparée mais pas transmise : la CA3 se saisit sur TeleDEC (pas d'envoi EDI), pas de CA12 annuelle.",
  "Pas de paiement en ligne propre : les adhésions et dons en ligne passent par HelloAsso.",
  "Modèles de reçus fiscaux à faire relire face aux formulaires Cerfa en vigueur avant usage.",
];

const MARK_LABEL: Record<Mark, string> = { yes: "oui", partial: "en partie", no: "non" };

function Glyph({ mark }: { mark: Mark | null }) {
  return mark === "yes" ? <Text span c="var(--lv-lichen)" fw={700}>✓</Text>
    : mark === "partial" ? <Text span c="var(--lv-paille-ink)" fw={600} fz={17} lh={1}>◐</Text>
      : mark === "no" ? <Text span c="var(--lv-brique)">✕</Text>
        : <Text span c="dimmed" size="xs">·</Text>;
}

/** Case d'un concurrent : la justification en infobulle, la page de l'éditeur en lien. */
function EvidenceCell({ evidence }: { evidence?: Evidence }) {
  if (!evidence) return <Table.Td ta="center" aria-label="non trouvé chez l'éditeur"><Glyph mark={null} /></Table.Td>;
  return (
    <Table.Td ta="center">
      <Tooltip label={evidence.why} multiline w={280} withArrow events={{ hover: true, focus: true, touch: true }}>
        <Anchor href={evidence.url} target="_blank" rel="noreferrer" underline="never"
          aria-label={`${MARK_LABEL[evidence.mark]} : ${evidence.why}`}><Glyph mark={evidence.mark} /></Anchor>
      </Tooltip>
    </Table.Td>
  );
}

/** Tableau Lyvre / autres logiciels : une ligne par critère, une colonne par logiciel. */
function ComparisonTable({ rows, vendors }: { rows: Row[]; vendors: Vendor[] }) {
  return (
    <Paper p={0} mb="xs" style={{ overflowX: "auto" }}>
      <Table verticalSpacing={6} miw={900} stickyHeader>
        <Table.Thead bg="var(--lv-surface)">
          <Table.Tr>
            <Table.Th />
            <Table.Th ta="center" bg="var(--lv-sauge)">Lyvre</Table.Th>
            {vendors.map((v) => (
              <Table.Th key={v.name} ta="center">
                <Tooltip label={v.offer} multiline w={280} withArrow>
                  <Anchor href={v.site} target="_blank" rel="noreferrer" c="inherit" fw={600} size="sm">{v.name}</Anchor>
                </Tooltip>
              </Table.Th>
            ))}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((row) => (
            <Table.Tr key={row.key}>
              <Table.Td><Text size="sm">{row.label}</Text>{row.note && <Text size="xs" c="dimmed">{row.note}</Text>}</Table.Td>
              <Table.Td ta="center" bg="var(--lv-sauge)" aria-label={MARK_LABEL[row.lyvre]}><Glyph mark={row.lyvre} /></Table.Td>
              {vendors.map((v) => <EvidenceCell key={v.name} evidence={v.criteria[row.key]} />)}
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Paper>
  );
}

export default function AboutPage() {
  const dark = useComputedColorScheme("light") === "dark";
  const { data: session } = useSession();
  const signedIn = !!session?.user;
  const app = useQuery({ queryKey: ["app-version"], staleTime: Infinity,
    queryFn: () => api.get<{ version: string; commit: string }>("/api/v1/version", { redirect: false }) });
  return (
    <Box bg="var(--lv-paper)" mih="100vh">
      <Container size="lg" py="md">
        <Group justify="space-between">
          <Group gap="sm"><Image src={dark ? symbolInverse : symbol} w={36} h={36} alt="" /><Wordmark /></Group>
          <Button component="a" href={signedIn ? "/" : "/login"}>{signedIn ? "Ouvrir l'application" : "Se connecter"}</Button>
        </Group>

        <Stack gap="xs" mt={48} mb={40} maw={760}>
          <Badge variant="light" color="lichen" w="fit-content">Logiciel libre · AGPL-3.0 · auto-hébergé</Badge>
          <Title order={1} fz={{ base: 32, sm: 42 }} lh={1.15}>La comptabilité innovante, libre, sobre et souveraine.</Title>
          <Text size="lg" c="dimmed">
            Lyvre tient la comptabilité d'une association, d'une SCI, d'une exploitation agricole ou d'une entreprise de
            services, de la saisie au bilan : banque et caisse, achats et ventes, facture électronique, adhésions et
            dons, baux, échéancier, activités et stocks, immobilisations, clôture et FEC pour l'expert-comptable. En
            partie double, ou simplifiée pour les petites structures.
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
          Logiciels cités par deux comparatifs publics, fonctionnalités vérifiées sur les sites et centres d'aide des
          éditeurs le {CHECKED_ON}. Survolez une case pour la justification, cliquez pour la page source. Un point « · »
          signifie que rien n'a été trouvé chez l'éditeur, pas que la fonctionnalité est absente ; les offres évoluent.
        </Text>
        <ComparisonTable rows={ROWS} vendors={VENDORS} />
        <Text size="xs" c="dimmed" mb={48}>✓ oui · ◐ en partie, option payante ou module tiers · ✕ non · « · » non trouvé. Aussi cités :
          MaCotisation (cotisations, logiciel comptable intégré), Ma Compta Association (catégories, rapport d'AG,
          installation locale), Sage 50 (comptabilité d'engagement, stocks).</Text>

        <Title order={2} mb={4}>Lyvre et les autres logiciels open source</Title>
        <Text size="sm" c="dimmed" mb="md" maw={820}>
          Logiciels de gestion dont le code source est publié, examinés le {CHECKED_ON} sur leur documentation et leur
          code (lu sans être exécuté). Plusieurs sont des ERP ou des outils de facturation plutôt que des logiciels de
          comptabilité associative : la ligne « Plan comptable associatif » fait la différence. Survolez un nom pour la
          licence et l'offre, une case pour la justification.
        </Text>
        <ComparisonTable rows={OSS_ROWS} vendors={OSS_VENDORS} />
        <Text size="xs" c="dimmed" mb={48}>✓ oui · ◐ en partie, option payante ou module tiers · ✕ non · « · » non trouvé.
          Invoice Ninja publie son code sous Elastic License 2.0, qui n'est pas une licence libre ; le dépôt de bureau de
          Frappe Books est archivé depuis le 02/10/2026.</Text>

        <SimpleGrid cols={{ base: 1, md: 2 }} mb={48}>
          <Paper p="md">
            <Group gap="xs" mb="xs"><ThemeIcon variant="light" color="lichen" radius="md"><BadgeCheck size={18} /></ThemeIcon>
              <Title order={3} size="h4">Ce qui distingue Lyvre</Title></Group>
            <List size="sm" spacing={4}>
              <List.Item>Libre et auto-hébergé : vos données restent chez vous, sans abonnement.</List.Item>
              <List.Item>Clôture complète guidée et FEC, comme un logiciel d'expert-comptable.</List.Item>
              <List.Item>Rapprochement bancaire au clavier, lecture des factures, règles automatiques.</List.Item>
              <List.Item>Plusieurs structures et rôles par structure, dont l'expert-comptable en lecture seule.</List.Item>
              <List.Item>Pour une SCI : baux, carte des parcelles, signature électronique et révision des loyers.</List.Item>
              <List.Item>Tiers pré-remplis depuis Sirene, adhérents synchronisés vers Brevo.</List.Item>
              <List.Item>Partie double ou simplifiée, avec passage de l'une à l'autre sans ressaisie.</List.Item>
              <List.Item>Pour une exploitation : échéancier fiscal, MSA et PAC, inventaire, marges par activité et assistant.</List.Item>
              <List.Item>Arrivée depuis Ekylibre en une restauration contrôlée, soldes vérifiés compte par compte.</List.Item>
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
            Independant.io, « Logiciel comptabilité association »</Anchor> — choix des logiciels comparés.</List.Item>
          <List.Item>Sites et centres d'aide des éditeurs, consultés le {CHECKED_ON} : chaque case du tableau renvoie à sa page.</List.Item>
          <List.Item>Logiciels open source : documentation et dépôts de code publics, consultés le {CHECKED_ON} ; chaque case renvoie à sa page.</List.Item>
        </List>
        <Text size="sm" fw={600} mb={4}>Icônes</Text>
        <List size="xs" c="dimmed" mb={40}>
          <List.Item><Anchor href="https://lucide.dev" target="_blank" rel="noreferrer" size="xs">Lucide</Anchor>
            {" "}— icônes de l'interface, licence ISC.</List.Item>
          <List.Item><Anchor href="https://github.com/ekylibre/agric" target="_blank" rel="noreferrer" size="xs">agric</Anchor>
            {" "}(Ekylibre, © 2013 Brice Texier) — pictogrammes agricoles, licence MIT.</List.Item>
        </List>
        <Text size="xs" c="dimmed" ta="center" pb="lg">LOGICIEL LIBRE · AGPL-3.0 · AUTO-HÉBERGÉ
          {app.data && <> · VERSION {app.data.version}{app.data.commit && ` (${app.data.commit.slice(0, 7)})`}</>}</Text>
      </Container>
    </Box>
  );
}
