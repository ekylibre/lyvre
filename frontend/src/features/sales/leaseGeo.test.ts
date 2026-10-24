// Lot L3 : surfaces, regroupement de la sélection, parcelles touchées par une zone dessinée.
import { describe, expect, it } from "vitest";
import type { FeatureCollection, Polygon } from "geojson";
import { areaM2, combine, iduFromRef, touchedRefs, type ParcelProps } from "./leaseGeo";

const square = (x: number, y: number, size: number): Polygon => ({ type: "Polygon",
  coordinates: [[[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]] });
const parcel = (ref: string, shape: Polygon) => ({ type: "Feature" as const, id: ref, geometry: shape,
  properties: { idu: ref, ref, insee: "17387", commune: "Saint-Porchaire", area_m2: null } });
const PARCELS: FeatureCollection<Polygon, ParcelProps> = { type: "FeatureCollection", features: [
  parcel("AH 248", square(-0.784, 45.827, 0.001)), parcel("AH 250", square(-0.783, 45.827, 0.001)),
  parcel("AH 59", square(-0.790, 45.820, 0.001)),
] };

describe("géométrie des biens", () => {
  it("surface géodésique en m²", () => {
    const a = areaM2(square(-0.784, 45.827, 0.001));  // 0,001° ≈ 78 m × 111 m à cette latitude
    expect(a).toBeGreaterThan(8500);
    expect(a).toBeLessThan(8800);
  });

  it("sélection regroupée en multipolygone", () => {
    const one = square(0, 0, 1);
    expect(combine([one])).toBe(one);
    const both = combine([one, square(2, 0, 1)]);
    expect(both.type).toBe("MultiPolygon");
    expect(both.coordinates).toHaveLength(2);
  });

  it("zone à cheval sur deux parcelles : leurs deux références", () => {
    expect(touchedRefs(square(-0.7832, 45.8272, 0.0004), PARCELS)).toEqual(["AH 248", "AH 250"]);
    expect(touchedRefs(square(10, 10, 1), PARCELS)).toEqual([]);
    expect(touchedRefs(square(0, 0, 1), undefined)).toEqual([]);
  });

  it("identifiant cadastral depuis une référence saisie", () => {
    expect(iduFromRef("17387", "AH 248")).toBe("17387000AH0248");
    expect(iduFromRef("17387", "a12")).toBe("173870000A0012");
    expect(iduFromRef("17387", "AH")).toBeNull();
    expect(iduFromRef("", "AH 248")).toBeNull();
  });
});
