"""Front-end helpers shared by the HTML views.

HTMX conventions (see claudedocs/design_front_reactif.md §5):

- Lists, filters and forms swap the ``#page-content`` zone: the server
  renders the full page and HTMX keeps the zone (``hx-select``, macros in
  ``_list_helpers.html``).
- Flash messages of an HTMX response are sent as an ``HX-Trigger`` "toast"
  event instead of waiting for the next full page.
- A redirect answering an HTMX request is never followed silently by the
  browser (HTMX would swap the whole target page, e.g. the login page, into
  the fragment zone):
  - request targeting the content zone (``#page-content``, see the
    ``hx_nav`` / ``hx_submit`` macros) → ``HX-Location``: HTMX loads the new
    page with an AJAX request, swaps only the content zone and pushes the URL;
  - otherwise, or towards the login / instance selection pages →
    ``HX-Redirect`` (full page navigation).
"""
import json
import os
from urllib.parse import urlsplit

from flask import current_app, get_flashed_messages, request, url_for
from markupsafe import Markup, escape

CONTENT_ZONE = "page-content"


# ---------------------------------------------------------------------------
# React islands assets (Vite) — see frontend/vite.config.ts
# ---------------------------------------------------------------------------

VITE_ENTRY = "src/main.tsx"
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


def vite_assets(entry=VITE_ENTRY):
    """<script>/<link> tags loading the islands bundle.

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
            '<div class="alert alert-danger" role="alert">'
            "Interface indisponible : les fichiers du front ne sont pas construits "
            "(<code>npm --prefix frontend run build</code>)."
            "</div>"
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


def is_htmx() -> bool:
    """True for a request issued by HTMX (outside of hx-boost navigation)."""
    return bool(request.headers.get("HX-Request")) and not request.headers.get("HX-Boosted")


def _merge_trigger(response, name, value):
    """Add an event to the response ``HX-Trigger`` header, keeping existing ones."""
    raw = response.headers.get("HX-Trigger")
    events = {}
    if raw:
        try:
            parsed = json.loads(raw)
            events = parsed if isinstance(parsed, dict) else {}
        except ValueError:
            # Plain comma-separated event names.
            events = {e.strip(): None for e in raw.split(",") if e.strip()}
    events[name] = value
    # ASCII-only JSON: HTTP header values must stay latin-1 safe.
    response.headers["HX-Trigger"] = json.dumps(events, ensure_ascii=True)


def _full_page_only(location):
    """Pages outside the main layout (no content zone to swap into)."""
    path = urlsplit(location).path
    return path in (url_for("auth.login"), url_for("auth.select_instance"))


def register_frontend(app):
    """HTMX response hook + Vite helpers for the templates."""
    app.config.setdefault("VITE_DEV_SERVER", os.environ.get("VITE_DEV_SERVER", ""))
    app.jinja_env.globals["vite_assets"] = vite_assets

    @app.after_request
    def _htmx_response(response):
        if not request.headers.get("HX-Request"):
            return response

        if 300 <= response.status_code < 400 and response.location:
            location = response.location
            response.status_code = 200
            response.headers.pop("Location", None)
            response.set_data(b"")
            target = request.headers.get("HX-Target")
            if target == CONTENT_ZONE and not _full_page_only(location):
                zone = f"#{CONTENT_ZONE}"
                response.headers["HX-Location"] = json.dumps({
                    "path": location, "target": zone, "select": zone,
                    "swap": "outerHTML show:none",
                })
            else:
                response.headers["HX-Redirect"] = location
            # Flash messages stay in the session: they are sent with the
            # follow-up request (HX-Location) or shown on the next full page.
            return response

        messages = get_flashed_messages(with_categories=True)
        if messages:
            _merge_trigger(
                response,
                "toast",
                [{"level": category, "message": message} for category, message in messages],
            )
        return response
