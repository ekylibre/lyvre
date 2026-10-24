// Géométrie des biens loués (lot L3) : surfaces (Turf, géodésiques), regroupement d'une sélection
// en multipolygone, parcelles touchées par une zone (références cadastrales).
import area from "@turf/area";
import booleanIntersects from "@turf/boolean-intersects";
import type { Feature, FeatureCollection, MultiPolygon, Polygon } from "geojson";

export type Shape = Polygon | MultiPolygon;
export interface ParcelProps { idu: string; ref: string; insee: string | null; commune: string | null; area_m2: number | null }
export interface BuildingProps { id: string; nature: string | null; usage: string | null; height: number | null }

/** Surface en m², arrondie au m². */
export function areaM2(shape: Shape): number {
  return Math.round(area({ type: "Feature", geometry: shape, properties: {} }));
}

/** Plusieurs polygones (parcelles, bâtiments) en un seul multipolygone. */
export function combine(shapes: Shape[]): Shape {
  if (shapes.length === 1) return shapes[0];
  return { type: "MultiPolygon", coordinates: shapes.flatMap((s) => s.type === "Polygon" ? [s.coordinates] : s.coordinates) };
}

/** Références des parcelles chargées que la zone touche (« AH 248 »), sans doublon, triées. */
export function touchedRefs(zone: Shape, parcels: FeatureCollection<Shape, ParcelProps> | undefined): string[] {
  if (!parcels) return [];
  const zoneFeature: Feature<Shape> = { type: "Feature", geometry: zone, properties: {} };
  const refs = parcels.features.filter((p) => booleanIntersects(zoneFeature, p)).map((p) => p.properties.ref);
  return [...new Set(refs)].sort((a, b) => a.localeCompare(b, "fr", { numeric: true }));
}

/** Identifiant cadastral depuis le code commune, la section et le numéro saisis (« AH 248 »). */
export function iduFromRef(insee: string, ref: string): string | null {
  // Section : une ou deux lettres, ou un chiffre et une lettre (« AH », « 0A ») ; puis le numéro.
  const m = ref.trim().toUpperCase().match(/^([A-Z]{1,2}|[0-9][A-Z])\s*0*(\d{1,4})$/);
  if (!m || !/^\d{5}$/.test(insee)) return null;
  return `${insee}000${m[1].padStart(2, "0")}${m[2].padStart(4, "0")}`;
}
