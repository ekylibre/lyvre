"""Front-end helpers shared by the HTML views.

HTMX conventions (see claudedocs/design_front_reactif.md §5):

- ``render_page`` returns only the fragment template for an HTMX request,
  the full page otherwise (the page includes the fragment).
- Flash messages of an HTMX response are sent as an ``HX-Trigger`` "toast"
  event instead of waiting for the next full page.
- A redirect answering an HTMX request becomes an ``HX-Redirect`` (full page
  navigation): otherwise the browser would follow it silently and HTMX would
  swap the whole target page (e.g. the login page) into the fragment zone.
"""
import json

from flask import get_flashed_messages, render_template, request


def is_htmx() -> bool:
    """True for a request issued by HTMX (outside of hx-boost navigation)."""
    return bool(request.headers.get("HX-Request")) and not request.headers.get("HX-Boosted")


def render_page(template, partial, **context):
    """Render ``partial`` alone for an HTMX request, ``template`` otherwise."""
    return render_template(partial if is_htmx() else template, **context)


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


def register_htmx_hooks(app):
    @app.after_request
    def _htmx_response(response):
        if not request.headers.get("HX-Request"):
            return response

        if 300 <= response.status_code < 400 and response.location:
            location = response.location
            response.status_code = 200
            response.headers.pop("Location", None)
            response.headers["HX-Redirect"] = location
            response.set_data(b"")
            # Flash messages stay in the session for the next full page.
            return response

        messages = get_flashed_messages(with_categories=True)
        if messages:
            _merge_trigger(
                response,
                "toast",
                [{"level": category, "message": message} for category, message in messages],
            )
        return response
