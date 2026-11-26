// Changements de TVA d'un exercice ouvert : un bouton dans la ligne, les choix dans son menu (l'état est affiché
// dans la colonne « TVA »).
import { Button, Menu } from "@mantine/core";

export type VatPeriod = "monthly" | "quarterly" | "annual";
export type VatPatch = { vat_liable: boolean } | { vat_on_receipts: boolean } | { vat_period: VatPeriod | null };
type Fy = { label: string; vat_liable: boolean; vat_on_receipts?: boolean | null; vat_period?: VatPeriod | null };

const PERIODS: { value: VatPeriod; label: string; title: string; agriOnly?: boolean }[] = [
  { value: "monthly", label: "Déclaration mensuelle (CA3)",
    title: "Prépare la déclaration de TVA de chaque mois (Compta › Déclarations de TVA)" },
  { value: "quarterly", label: "Trimestrielle (CA3)",
    title: "Régime simplifié agricole sur option : CA3 de chaque trimestre, remboursement de crédit possible" },
  { value: "annual", label: "Annuelle (CA12A)", agriOnly: true,
    title: "Régime simplifié agricole : déclaration annuelle CA12A et acomptes trimestriels" },
];

export function VatMenu({ fy, agri, simple, loading, onChange }: {
  fy: Fy; agri: boolean; simple: boolean; loading?: boolean; onChange: (patch: VatPatch) => void;
}) {
  const periods = PERIODS.filter((p) => (agri || !p.agriOnly) && p.value !== fy.vat_period);
  return (
    <Menu position="bottom-end" withinPortal>
      <Menu.Target>
        <Button variant="subtle" size="compact-sm" loading={loading} aria-label={`TVA, exercice ${fy.label}`}>TVA</Button>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Item title="S'applique aux factures comptabilisées à partir de maintenant"
          onClick={() => onChange({ vat_liable: !fy.vat_liable })}>
          {fy.vat_liable ? "Déclarer non soumis" : "Déclarer soumis"}
        </Menu.Item>
        {fy.vat_liable && <Menu.Item title="TVA des prestations de services ; s'applique aux factures de vente émises à partir de maintenant"
          onClick={() => onChange({ vat_on_receipts: fy.vat_on_receipts === false })}>
          {fy.vat_on_receipts === false ? "TVA à l'encaissement" : "Option TVA sur les débits"}
        </Menu.Item>}
        {fy.vat_liable && !simple && <>
          <Menu.Divider />
          <Menu.Label>Rythme de déclaration</Menu.Label>
          {periods.map((p) => <Menu.Item key={p.value} title={p.title}
            onClick={() => onChange({ vat_period: p.value })}>{p.label}</Menu.Item>)}
          {fy.vat_period && <Menu.Item onClick={() => onChange({ vat_period: null })}>Ne plus préparer la déclaration</Menu.Item>}
        </>}
      </Menu.Dropdown>
    </Menu>
  );
}
