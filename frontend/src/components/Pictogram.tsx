// Pictogramme agric (lot NV4, claudedocs/design_navigation.md § 5.2) : SVG plein en `currentColor`, décoratif.
// Les formes blanches de l'original deviennent des découpes (masque), pour rester justes sur fond teinté.
import { useId } from "react";
import { PICTOGRAMS } from "./pictograms.generated";

export function Pictogram({ name, size = 22 }: { name: string; size?: number }) {
  const maskId = useId();
  const data = PICTOGRAMS[name];
  if (!data) return null;
  const [, , w, h] = data.viewBox.split(" ").map(Number);
  return (
    <svg width={size} height={size} viewBox={data.viewBox} fill="currentColor" aria-hidden focusable="false"
      data-pictogram={name}>
      {data.cuts.length > 0 && (
        <mask id={maskId}>
          <rect width={w} height={h} fill="white" />
          {data.cuts.map((d, i) => <path key={i} d={d} fill="black" />)}
        </mask>
      )}
      <g mask={data.cuts.length ? `url(#${maskId})` : undefined}>
        {data.paths.map((d, i) => <path key={i} d={d} />)}
      </g>
    </svg>
  );
}
