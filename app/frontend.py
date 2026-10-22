"""Assets de la SPA (Vite) pour la coquille `spa.html` : manifeste du build en production,
serveur de développement Vite avec rechargement à chaud sinon (frontend/vite.config.ts)."""
import json
import os

from flask import current_app, url_for
from markupsafe import Markup, escape


SPA_ENTRY = "src/main.tsx"
_manifest_cache = {"mtime": None, "data": None}


def _manifest_path():
    return os.path.join(current_app.static_folder, "dist", ".vite", "manifest.json")


def _load_manifest():
    """Vite manifest, cached until the file changes (new build)."""
    path = _manifest_path()
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    if _manifest_cache["mtime"] != mtime:
        with open(path, encoding="utf-8") as fh:
            _manifest_cache["data"] = json.load(fh)
        _manifest_cache["mtime"] = mtime
    return _manifest_cache["data"]


def vite_assets(entry=SPA_ENTRY):
    """<script>/<link> tags loading the SPA bundle (app/templates/spa.html).

    Development (``VITE_DEV_SERVER`` set, e.g. http://localhost:5173): scripts
    come from the Vite dev server, with the React Refresh preamble (HMR).
    Production: hashed files listed in the build manifest.
    """
    dev_server = (current_app.config.get("VITE_DEV_SERVER") or "").rstrip("/")
    if dev_server:
        base = f"{dev_server}/static/dist"
        return Markup(
            '<script type="module">'
            f'import RefreshRuntime from "{base}/@react-refresh";'
            "RefreshRuntime.injectIntoGlobalHook(window);"
            "window.$RefreshReg$ = () => {};"
            "window.$RefreshSig$ = () => (type) => type;"
            "window.__vite_plugin_react_preamble_installed__ = true;"
            "</script>\n"
            f'<script type="module" src="{base}/@vite/client"></script>\n'
            f'<script type="module" src="{base}/{entry}"></script>'
        )

    manifest = _load_manifest()
    chunk = (manifest or {}).get(entry)
    if chunk is None:
        current_app.logger.error("Vite manifest missing or without %s: run `npm run build`", entry)
        return Markup(
            '<p role="alert" style="font-family:sans-serif;color:#9b3b2a">'
            "Interface indisponible : les fichiers du front ne sont pas construits "
            "(<code>npm --prefix frontend run build</code>)."
            "</p>"
        )

    def asset(path):
        return url_for("static", filename=f"dist/{path}")

    tags = [f'<link rel="stylesheet" href="{escape(asset(css))}">' for css in chunk.get("css", [])]
    for imported in chunk.get("imports", []):
        dep = manifest.get(imported, {})
        tags += [f'<link rel="stylesheet" href="{escape(asset(css))}">' for css in dep.get("css", [])]
        if dep.get("file"):
            tags.append(f'<link rel="modulepreload" href="{escape(asset(dep["file"]))}">')
    tags.append(f'<script type="module" src="{escape(asset(chunk["file"]))}"></script>')
    return Markup("\n".join(tags))


def register_frontend(app):
    """Helpers Vite pour les gabarits (`spa.html`)."""
    app.config.setdefault("VITE_DEV_SERVER", os.environ.get("VITE_DEV_SERVER", ""))
    app.jinja_env.globals["vite_assets"] = vite_assets
    app.jinja_env.globals["spa_entry"] = SPA_ENTRY
