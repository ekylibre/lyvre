"""Rendu SVG des graphes du rapport (pour le PDF serveur weasyprint).

weasyprint n'exécute pas de JavaScript : les graphes ECharts (rendus en JS dans
le navigateur) ne s'affichent pas dans un PDF généré côté serveur. Ce module
reconstruit un SVG statique à partir du **même dictionnaire d'options ECharts**
déjà produit par `activity_report_service` (séries `bar` / `line`+`area`,
axe catégoriel, multi-séries groupées), sans dépendance externe.
"""
from markupsafe import escape

AXIS = "#cdbf9f"
GRID = "#e7dcc4"
INK = "#5b5446"
GREEN = "#1c7a33"

W, H = 680, 280
PAD_L, PAD_R, PAD_T, PAD_B = 52, 16, 34, 42


def _nice_max(value):
    """Plafond « rond » (1/2/5 × 10ⁿ) au-dessus de `value`."""
    if value <= 0:
        return 1.0
    import math
    exp = math.floor(math.log10(value))
    base = 10 ** exp
    for m in (1, 2, 2.5, 5, 10):
        if value <= m * base:
            return m * base
    return 10 * base


def _fmt(v):
    if v == int(v):
        return str(int(v))
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _series_color(s):
    return (s.get("itemStyle", {}).get("color")
            or s.get("lineStyle", {}).get("color")
            or GREEN)


def option_to_svg(option):
    """Convertit un dict d'options ECharts en SVG inline (chaîne)."""
    labels = list((option.get("xAxis") or {}).get("data") or [])
    series = option.get("series") or []
    if not labels or not series:
        return ""

    vmax = 0.0
    for s in series:
        for v in (s.get("data") or []):
            if v is not None:
                vmax = max(vmax, float(v))
    top = _nice_max(vmax)

    plot_w = W - PAD_L - PAD_R
    plot_h = H - PAD_T - PAD_B
    x0, y0 = PAD_L, PAD_T
    y1 = PAD_T + plot_h

    def yof(v):
        return y1 - (float(v) / top) * plot_h

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="100%" font-family="sans-serif">'
    ]

    # Axe Y : lignes + libellés.
    steps = 4
    for i in range(steps + 1):
        val = top * i / steps
        y = yof(val)
        parts.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x0 + plot_w}" y2="{y:.1f}" '
                     f'stroke="{GRID}" stroke-width="1"/>')
        parts.append(f'<text x="{x0 - 6}" y="{y + 3:.1f}" text-anchor="end" '
                     f'font-size="10" fill="{INK}">{escape(_fmt(val))}</text>')

    n = len(labels)
    slot = plot_w / n
    bar_series = [s for s in series if s.get("type", "bar") == "bar"]
    line_series = [s for s in series if s.get("type") == "line"]

    # Barres groupées par catégorie.
    if bar_series:
        group_w = slot * 0.62
        bw = group_w / len(bar_series)
        for si, s in enumerate(bar_series):
            color = _series_color(s)
            data = s.get("data") or []
            for i in range(n):
                v = data[i] if i < len(data) else None
                if v is None or float(v) <= 0:
                    continue
                cx = x0 + slot * i + (slot - group_w) / 2 + si * bw
                y = yof(v)
                parts.append(f'<rect x="{cx:.1f}" y="{y:.1f}" width="{bw - 2:.1f}" '
                             f'height="{y1 - y:.1f}" fill="{color}"/>')

    # Courbes (option zone de remplissage).
    for s in line_series:
        color = _series_color(s)
        data = s.get("data") or []
        pts = []
        for i in range(n):
            v = data[i] if i < len(data) else None
            if v is None:
                continue
            cx = x0 + slot * i + slot / 2
            pts.append((cx, yof(v)))
        if not pts:
            continue
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        if s.get("areaStyle") is not None:
            area = f"{pts[0][0]:.1f},{y1:.1f} " + poly + f" {pts[-1][0]:.1f},{y1:.1f}"
            parts.append(f'<polygon points="{area}" fill="{color}" fill-opacity="0.12"/>')
        parts.append(f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="2"/>')
        for x, y in pts:
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}"/>')

    # Axe X (ligne + libellés).
    parts.append(f'<line x1="{x0}" y1="{y1:.1f}" x2="{x0 + plot_w}" y2="{y1:.1f}" '
                 f'stroke="{AXIS}" stroke-width="1"/>')
    for i, lab in enumerate(labels):
        cx = x0 + slot * i + slot / 2
        parts.append(f'<text x="{cx:.1f}" y="{y1 + 14:.1f}" text-anchor="middle" '
                     f'font-size="10" fill="{INK}">{escape(str(lab))}</text>')

    # Légende (séries nommées).
    named = [s for s in series if s.get("name")]
    if len(named) > 1:
        lx = x0
        for s in named:
            color = _series_color(s)
            parts.append(f'<rect x="{lx}" y="6" width="10" height="10" fill="{color}"/>')
            parts.append(f'<text x="{lx + 14}" y="15" font-size="10" fill="{INK}">'
                         f'{escape(str(s["name"]))}</text>')
            lx += 16 + 7 * len(str(s["name"])) + 14

    parts.append("</svg>")
    return "".join(parts)
