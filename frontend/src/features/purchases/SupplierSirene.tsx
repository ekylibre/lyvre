// Facture d'achat › Fournisseur : « Chercher dans Sirene » (lot G4, D9). Un fournisseur déjà connu
// (même SIREN) est choisi tel quel, sans être modifié ; sinon la facture crée le tiers à son
// enregistrement, avec la fiche Sirene (B19 : rien n'est créé avant la confirmation).
import { useState } from "react";
import { Alert, Button, Loader, Stack, Text } from "@mantine/core";
import { FormModal } from "../../components/FormModal";
import { SireneSearch } from "../../components/sirene/SireneSearch";
import { sireneMessage, useSireneAvailable, useSireneProposal, type SireneCandidate } from "../../components/sirene/useSirene";

/** Fournisseur trouvé : tiers existant, ou fiche du tiers à créer. */
export type SupplierChoice =
  | { kind: "known"; id: number; name: string }
  | { kind: "new"; name: string; siret: string; vat: string; entity: Record<string, string> };

const ENTITY_KEYS = ["siren", "address_line1", "address_line2", "postal_code", "city", "country", "naf_code",
  "naf_nomenclature", "person_kind"];

export function SupplierSirene({ initialQuery, onChoose }: { initialQuery: string; onChoose: (choice: SupplierChoice) => void }) {
  const available = useSireneAvailable();
  const [opened, setOpened] = useState(false);
  const proposal = useSireneProposal();
  if (!available) return null;
  const pick = (c: SireneCandidate) => proposal.mutate({ ...(c.siret ? { siret: c.siret } : { siren: c.siren }), for: "entity" }, {
    onSuccess: (r) => {
      const p = r.proposal;
      onChoose(r.existing_entity ? { kind: "known", ...r.existing_entity }
        : { kind: "new", name: p.name, siret: p.siret ?? "", vat: p.vat_number ?? "",
          entity: Object.fromEntries(ENTITY_KEYS.filter((k) => p[k]).map((k) => [k, p[k]])) });
      setOpened(false);
    },
  });
  return (
    <>
      <Button variant="light" size="compact-sm" onClick={() => setOpened(true)}>Chercher dans Sirene</Button>
      <FormModal opened={opened} onClose={() => setOpened(false)} title="Fournisseur dans Sirene" size="lg">
        <Stack>
          <SireneSearch onPick={pick} initialQuery={initialQuery} />
          {proposal.isPending && <Loader size="sm" />}
          {proposal.isError && <Alert color="brique" role="alert">{sireneMessage(proposal.error)}</Alert>}
          <Text size="xs" c="dimmed">Un fournisseur déjà enregistré avec ce SIREN est repris sans être modifié ; sinon il sera
            créé avec la fiche Sirene à l'enregistrement de la facture.</Text>
        </Stack>
      </FormModal>
    </>
  );
}
