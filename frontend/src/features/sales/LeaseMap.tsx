// Carte des biens loués (lot L3, BF2–BF6) : photo aérienne IGN, couche des parcelles (IGN) ou des
// bâtiments (BD TOPO), sélection de plusieurs éléments, zone dessinée (Bâtiment ou Sol) ; la fiche
// Lexicon de la parcelle cliquée donne sa surface et l'emprise de ses bâtiments. « Valider la
// sélection » ouvre la ligne du bail pré-remplie (surface, références cadastrales, géométrie).
// Chargée à la demande (morceau séparé) : Leaflet n'est pas dans le reste de l'application.
import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "@geoman-io/leaflet-geoman-free";
import "@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css";
import { Alert, Badge, Button, Grid, Group, Paper, SegmentedControl, Stack, Text, TextInput } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import type { Feature, FeatureCollection } from "geojson";
import { api, ApiError } from "../../api/client";
import { areaM2, combine, iduFromRef, touchedRefs, type BuildingProps, type ParcelProps, type Shape } from "./leaseGeo";
import type { LeaseItem } from "./types";
import "./leaseMap.css";

export interface ItemPrefill {
  label: string; nature: "building" | "land"; area_m2: number; built_m2: number; cadastral_refs: string[];
  geometry: Shape; source: "parcels" | "buildings" | "drawn";
}
interface Center { lat: number; lon: number; zoom: number; label: string; insee?: string }
interface ParcelCard { idu: string; ref: string; area_m2: number | null; buildings: number; buildings_area_m2: number; commune: string | null }
type Mode = "parcels" | "buildings" | "draw";
type Selected = Feature<Shape, ParcelProps | BuildingProps>;

const MIN_ZOOM = 16;
const ORTHO = "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=ORTHOIMAGERY.ORTHOPHOTOS"
  + "&STYLE=normal&TILEMATRIXSET=PM&FORMAT=image/jpeg&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}";
const ITEM_STYLE = { color: "#2832aa", weight: 2, fillColor: "#4650c8", fillOpacity: 0.4 };
const LAYER_STYLE = { color: "#ffffff", weight: 1, fillOpacity: 0.05 };
const SELECTED_STYLE = { color: "#ffb000", weight: 3, fillColor: "#ffb000", fillOpacity: 0.35 };
const m2 = (n: number) => `${n.toLocaleString("fr-FR")} m²`;

function bboxOf(map: L.Map) {
  const b = map.getBounds();
  return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map((n) => n.toFixed(4)).join(",");
}

function useLayer<T>(kind: "parcels" | "buildings", bbox: string | null) {
  return useQuery({
    queryKey: ["geo", kind, bbox], enabled: bbox !== null, staleTime: 15 * 60_000, retry: false,
    queryFn: () => api.get<FeatureCollection<Shape, T>>(`/api/v1/geo/${kind}?bbox=${bbox}`),
  });
}

export default function LeaseMap({ items, onPick }: { items: LeaseItem[]; onPick: (prefill: ItemPrefill) => void }) {
  const center = useQuery({ queryKey: ["geo", "organization"], staleTime: Infinity,
    queryFn: () => api.get<{ center: Center }>("/api/v1/geo/organization") });
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const dataLayer = useRef<L.GeoJSON | null>(null);
  const itemsLayer = useRef<L.GeoJSON | null>(null);
  const drawnLayer = useRef<L.Layer | null>(null);
  const fitted = useRef(false);
  const [mode, setMode] = useState<Mode>("parcels");
  const [view, setView] = useState<{ bbox: string; zoom: number } | null>(null);
  const [selected, setSelected] = useState<Selected[]>([]);
  const [cards, setCards] = useState<Record<string, ParcelCard>>({});
  const [drawn, setDrawn] = useState<Shape | null>(null);
  const [drawNature, setDrawNature] = useState<"building" | "land">("land");
  const [ref, setRef] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const zoomOk = (view?.zoom ?? 0) >= MIN_ZOOM;
  const parcels = useLayer<ParcelProps>("parcels", zoomOk ? view!.bbox : null);
  const buildings = useLayer<BuildingProps>("buildings", zoomOk && mode === "buildings" ? view!.bbox : null);
  const layerError = (parcels.error ?? buildings.error) as ApiError | null;

  // Carte : créée une fois le centre connu ; vue sur les biens déjà dessinés s'il y en a.
  useEffect(() => {
    if (!container.current || mapRef.current || !center.data) return;
    const c = center.data.center;
    const map = L.map(container.current, { center: [c.lat, c.lon], zoom: c.zoom, maxZoom: 21 });
    L.tileLayer(ORTHO, { maxNativeZoom: 19, maxZoom: 21, attribution: "© IGN — Géoplateforme · fiches de parcelles : Lexicon (osfarm)" }).addTo(map);
    const update = () => setView({ bbox: bboxOf(map), zoom: map.getZoom() });
    map.on("moveend", update);
    mapRef.current = map;
    update();
    return () => { map.remove(); mapRef.current = null; };
  }, [center.data]);

  // Biens du bail : zones bleues lettrées.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    itemsLayer.current?.remove();
    const features = items.filter((i) => i.geometry).map((i) => ({ type: "Feature" as const, geometry: i.geometry as Shape, properties: { letter: i.letter } }));
    const layer = L.geoJSON({ type: "FeatureCollection", features } as FeatureCollection, {
      style: () => ITEM_STYLE, interactive: false,
      onEachFeature: (f, l) => { if (f.properties.letter) l.bindTooltip(f.properties.letter, { permanent: true, direction: "center", className: "lease-letter" }); },
    }).addTo(map);
    itemsLayer.current = layer;
    if (features.length && !fitted.current) map.fitBounds(layer.getBounds(), { maxZoom: 18, padding: [30, 30] });
    fitted.current = true;
  }, [items, center.data]);

  // Couche de sélection : parcelles ou bâtiments, éléments choisis en orange.
  const data = mode === "buildings" ? buildings.data : parcels.data;
  const selectedIds = useMemo(() => new Set(selected.map((f) => String(f.id))), [selected]);
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    dataLayer.current?.remove();
    dataLayer.current = null;
    if (!data || !zoomOk) return;
    const interactive = mode !== "draw";
    dataLayer.current = L.geoJSON(data as FeatureCollection, {
      interactive,
      style: (f) => (selectedIds.has(String(f?.id)) ? SELECTED_STYLE : LAYER_STYLE),
      onEachFeature: (f, l) => {
        if (!interactive) return;
        l.bindTooltip(mode === "parcels" ? (f.properties as ParcelProps).ref : ((f.properties as BuildingProps).usage ?? "Bâtiment"));
        l.on("click", (e: L.LeafletMouseEvent) => {
          setSelected((current) => current.some((s) => s.id === f.id) ? current.filter((s) => s.id !== f.id) : [...current, f as Selected]);
          if (mode === "parcels") loadCard(e.latlng.lat, e.latlng.lng);
        });
      },
    }).addTo(map);
    itemsLayer.current?.bringToFront();
  }, [data, mode, selectedIds, zoomOk]);

  // Zone dessinée (Geoman) : un polygone, modifiable jusqu'à validation.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (mode !== "draw") {
      map.pm.disableDraw();
      drawnLayer.current?.remove();
      drawnLayer.current = null;
      setDrawn(null);
      return;
    }
    const onCreate = (e: { layer: L.Layer }) => {
      drawnLayer.current?.remove();
      drawnLayer.current = e.layer;
      const layer = e.layer as L.Polygon;
      setDrawn(layer.toGeoJSON().geometry as Shape);
      layer.pm.enable();
      layer.on("pm:edit", () => setDrawn(layer.toGeoJSON().geometry as Shape));
    };
    map.on("pm:create", onCreate);
    if (!drawnLayer.current) map.pm.enableDraw("Polygon", { snappable: true });
    return () => { map.off("pm:create", onCreate); map.pm.disableDraw(); };
  }, [mode, center.data]);

  const changeMode = (next: Mode) => { setSelected([]); setMode(next); };
  /** Fiche Lexicon de la parcelle au point (surface, bâtiments) ; facultative : la carte s'en passe. */
  const loadCard = (lat: number, lon: number) => {
    void api.get<{ item: ParcelCard }>(`/api/v1/geo/parcel?lat=${lat.toFixed(6)}&lon=${lon.toFixed(6)}`)
      .then((r) => setCards((c) => ({ ...c, [r.item.idu]: r.item }))).catch(() => undefined);
  };
  const totalArea = selected.reduce((sum, f) => sum + ((f.properties as ParcelProps).area_m2 ?? areaM2(f.geometry)), 0);

  function validate() {
    if (mode === "draw" && drawn) {
      const area = areaM2(drawn);
      onPick({ label: "", nature: drawNature, area_m2: area, built_m2: drawNature === "building" ? area : 0,
        cadastral_refs: touchedRefs(drawn, parcels.data), geometry: drawn, source: "drawn" });
      changeMode("draw");
      drawnLayer.current?.remove();
      drawnLayer.current = null;
      setDrawn(null);
      mapRef.current?.pm.enableDraw("Polygon", { snappable: true });
      return;
    }
    const geometry = combine(selected.map((f) => f.geometry));
    if (mode === "parcels") {
      const props = selected.map((f) => f.properties as ParcelProps);
      onPick({ label: props.map((p) => p.ref).join(", "), nature: "land", area_m2: totalArea,
        built_m2: props.reduce((sum, p) => sum + (cards[p.idu]?.buildings_area_m2 ?? 0), 0),
        cadastral_refs: props.map((p) => p.ref), geometry, source: "parcels" });
    } else {
      const area = selected.reduce((sum, f) => sum + areaM2(f.geometry), 0);
      onPick({ label: "Bâtiment", nature: "building", area_m2: area, built_m2: area,
        cadastral_refs: touchedRefs(geometry, parcels.data), geometry, source: "buildings" });
    }
    setSelected([]);
  }

  async function addByRef() {
    const insee = parcels.data?.features[0]?.properties.insee ?? center.data?.center.insee ?? "";
    const idu = iduFromRef(insee, ref);
    if (!idu) { setMessage("Référence attendue : section et numéro, par exemple AH 248."); return; }
    try {
      const { item } = await api.get<{ item: Selected }>(`/api/v1/geo/parcel?ref=${idu}`);
      setMessage(null);
      setRef("");
      if (mode !== "parcels") changeMode("parcels");
      setSelected((current) => current.some((s) => s.id === item.id) ? current : [...current, item]);
      const bounds = L.geoJSON(item as Feature).getBounds();
      mapRef.current?.fitBounds(bounds, { maxZoom: 18 });
      loadCard(bounds.getCenter().lat, bounds.getCenter().lng);
    } catch (e) {
      setMessage((e as Error).message);
    }
  }

  if (center.isLoading) return <Text size="sm" c="dimmed">Chargement de la carte…</Text>;
  return (
    <Grid>
      <Grid.Col span={{ base: 12, md: 8 }}>
        <div ref={container} className="lease-map" data-testid="lease-map" />
      </Grid.Col>
      <Grid.Col span={{ base: 12, md: 4 }}>
        <Stack gap="sm">
          <SegmentedControl fullWidth value={mode} onChange={(v) => changeMode(v as Mode)} data={[
            { value: "parcels", label: "Parcelles" }, { value: "buildings", label: "Bâtiments" }, { value: "draw", label: "Dessiner" }]} />
          {!zoomOk && <Alert variant="light">Rapprochez-vous pour afficher les {mode === "buildings" ? "bâtiments" : "parcelles"}.</Alert>}
          {layerError && <Alert color="brique" variant="light">{layerError.message}</Alert>}
          {mode === "draw" ? (
            <Paper withBorder p="sm">
              <Stack gap="xs">
                <Text size="sm">Dessinez la zone louée point par point sur la carte (clic sur le premier point pour fermer) ;
                  ses sommets se déplacent ensuite.</Text>
                <SegmentedControl size="xs" value={drawNature} onChange={(v) => setDrawNature(v as "building" | "land")}
                  data={[{ value: "land", label: "Sol" }, { value: "building", label: "Bâtiment" }]} />
                {drawn && <Text size="sm">Zone de <b>{m2(areaM2(drawn))}</b>{parcels.data && <> · parcelles {touchedRefs(drawn, parcels.data).join(", ") || "—"}</>}</Text>}
              </Stack>
            </Paper>
          ) : (
            <Paper withBorder p="sm">
              {!selected.length ? <Text size="sm" c="dimmed">Cliquez {mode === "parcels" ? "une ou plusieurs parcelles" : "un ou plusieurs bâtiments"} pour les choisir.</Text> : (
                <Stack gap={4}>
                  {selected.map((f) => {
                    const p = f.properties as ParcelProps & BuildingProps;
                    const card = mode === "parcels" ? cards[p.idu] : undefined;
                    return (
                      <Group key={String(f.id)} justify="space-between" gap="xs" wrap="nowrap">
                        <Text size="sm">{mode === "parcels" ? p.ref : (p.usage ?? p.nature ?? "Bâtiment")}</Text>
                        <Text size="sm" className="lv-num">{m2(p.area_m2 ?? areaM2(f.geometry))}
                          {card && card.buildings > 0 && <Badge ml={6} size="xs" variant="light">{card.buildings} bât. · {m2(card.buildings_area_m2)}</Badge>}</Text>
                      </Group>);
                  })}
                  <Text size="sm" fw={600}>Total : {m2(totalArea)}</Text>
                </Stack>
              )}
            </Paper>
          )}
          <Button disabled={mode === "draw" ? !drawn : !selected.length} onClick={validate}>Valider la sélection</Button>
          <Group gap="xs" align="flex-end" wrap="nowrap">
            <TextInput label="Ajouter une parcelle par référence" placeholder="AH 248" value={ref} style={{ flex: 1 }}
              onChange={(e) => setRef(e.currentTarget.value)} />
            <Button variant="default" disabled={!ref.trim()} onClick={() => void addByRef()}>Ajouter</Button>
          </Group>
          {message && <Text size="sm" c="var(--lv-brique)">{message}</Text>}
        </Stack>
      </Grid.Col>
    </Grid>
  );
}
