// Carte des calculettes géographiques (lot AG12.d : 04 carte RPG, 07 zonages) : photo aérienne IGN, point choisi d'un
// clic (`onPick`), parcelles du résultat colorées par groupe de cultures. Chargée à la demande (Leaflet à part).
import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { FeatureCollection } from "geojson";

const ORTHO = "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=ORTHOIMAGERY.ORTHOPHOTOS"
  + "&STYLE=normal&TILEMATRIXSET=PM&FORMAT=image/jpeg&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}";
const POINT_STYLE = { radius: 7, color: "#ffffff", weight: 2, fillColor: "#d9480f", fillOpacity: 1 };

export interface CalcMapProps {
  center: [number, number]; zoom: number; point?: [number, number] | null;
  features?: FeatureCollection | null; onPick?: (lat: number, lon: number) => void; height?: number;
}

export default function CalcMap({ center, zoom, point, features, onPick, height = 320 }: CalcMapProps) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const marker = useRef<L.CircleMarker | null>(null);
  const layer = useRef<L.GeoJSON | null>(null);
  const pick = useRef(onPick);
  pick.current = onPick;

  useEffect(() => {
    if (!box.current || map.current) return;
    const m = L.map(box.current, { center, zoom, maxZoom: 19 });
    L.tileLayer(ORTHO, { maxZoom: 19, attribution: "© IGN" }).addTo(m);
    m.on("click", (e: L.LeafletMouseEvent) => pick.current?.(Number(e.latlng.lat.toFixed(6)), Number(e.latlng.lng.toFixed(6))));
    map.current = m;
    return () => { m.remove(); map.current = null; };
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    marker.current?.remove();
    marker.current = point ? L.circleMarker(point, POINT_STYLE).addTo(m) : null;
  }, [point]);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    layer.current?.remove();
    layer.current = features ? L.geoJSON(features, {
      style: (f) => ({ color: f?.properties?.color ?? "#ffffff", weight: 1, fillOpacity: 0.35 }),
      onEachFeature: (f, l) => { if (f.properties?.label) l.bindTooltip(String(f.properties.label)); },
    }).addTo(m) : null;
    marker.current?.bringToFront();
  }, [features]);

  useEffect(() => { map.current?.setView(center, zoom); }, [center[0], center[1], zoom]);  // eslint-disable-line react-hooks/exhaustive-deps

  return <div ref={box} style={{ height, borderRadius: 8 }} aria-label="Carte" />;
}
