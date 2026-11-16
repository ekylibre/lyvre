// Pastille d'icône (lot NV4, claudedocs/design_navigation.md § 5.2) : cartes, tuiles et en-têtes de page.
// Le pictogramme agric l'emporte sur l'icône Lucide ; rien n'est affiché sans l'un ni l'autre.
import { ThemeIcon } from "@mantine/core";
import { NavIcon } from "../app/navIcons";
import { Pictogram } from "./Pictogram";
import { PICTOGRAMS } from "./pictograms.generated";

export function IconTile({ icon, pictogram, size = 40, color = "lichen" }: {
  icon?: string; pictogram?: string; size?: number; color?: string;
}) {
  const inner = Math.round(size * 0.55);
  const glyph = pictogram && PICTOGRAMS[pictogram] ? <Pictogram name={pictogram} size={inner} />
    : icon ? <NavIcon name={icon} size={inner} /> : null;
  if (!glyph) return null;
  return (
    <ThemeIcon variant="light" color={color} size={size} radius="md" aria-hidden style={{ flexShrink: 0 }}>
      {glyph}
    </ThemeIcon>
  );
}
