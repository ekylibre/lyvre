// Logo d'une intégration sur une pastille blanche arrondie : lisible en thème clair et sombre sans
// variante du logo. SMTP (pas de marque) : enveloppe ; Documenso (serveur choisi par la structure) : stylo.
import { Center, Image } from "@mantine/core";
import { Mail, PenLine } from "lucide-react";
import { INTEGRATION_LOGOS, integrationLabel } from "./catalog";

export function IntegrationLogo({ slug, size = 40 }: { slug: string; size?: number }) {
  const src = INTEGRATION_LOGOS[slug];
  return (
    <Center w={size} h={size} bg="white" style={{ borderRadius: 8, flexShrink: 0, border: "1px solid var(--mantine-color-default-border)" }}>
      {src
        ? <Image src={src} alt={integrationLabel(slug)} w={size - 8} h={size - 8} fit="contain" />
        : slug === "documenso"
          ? <PenLine size={size * 0.55} color="#3B5A78" aria-label={integrationLabel(slug)} role="img" />
          : <Mail size={size * 0.55} color="#3B5A78" /* ardoise claire : la pastille reste blanche en thème sombre */ aria-label={integrationLabel(slug)} role="img" />}
    </Center>
  );
}
