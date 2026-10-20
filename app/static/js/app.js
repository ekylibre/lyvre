// ---------------------------------------------------------------------------
// HTMX conventions (see app/frontend.py). htmx is loaded with `defer`: only
// listen to DOM events here, never use the `htmx` global at load time.
// ---------------------------------------------------------------------------

// CSRF token on every HTMX request (Flask-WTF accepts the X-CSRFToken header).
document.addEventListener('htmx:configRequest', e => {
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta) e.detail.headers['X-CSRFToken'] = meta.content;
});

// Toasts: server-rendered flash messages + "toast" events sent by HX-Trigger.
const TOAST_DELAY_MS = 6000;

function initToast(el) {
  // Errors stay until dismissed; other messages hide by themselves.
  const autohide = el.dataset.level !== 'danger';
  bootstrap.Toast.getOrCreateInstance(el, { autohide, delay: TOAST_DELAY_MS }).show();
  el.addEventListener('hidden.bs.toast', () => el.remove());
}

function showToast(level, message) {
  const zone = document.getElementById('toast-zone');
  const tpl = document.getElementById('toast-template');
  if (!zone || !tpl) return;
  const el = tpl.content.firstElementChild.cloneNode(true);
  const known = ['success', 'danger', 'warning', 'info'];
  const lvl = known.includes(level) ? level : 'info';
  el.classList.replace('text-bg-info', `text-bg-${lvl}`);
  el.dataset.level = lvl;
  el.setAttribute('role', lvl === 'danger' ? 'alert' : 'status');
  el.querySelector('.toast-body').textContent = message;
  zone.appendChild(el);
  initToast(el);
}

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('#toast-zone .toast').forEach(initToast);
});

document.body.addEventListener('toast', e => {
  // HX-Trigger value: list of {level, message} (htmx passes it as event detail).
  const detail = e.detail;
  const items = Array.isArray(detail) ? detail : (detail && detail.value) || [];
  items.forEach(t => showToast(t.level, t.message));
});

document.addEventListener('htmx:responseError', e => {
  const status = e.detail.xhr.status;
  const message = status === 400
    ? 'Requête refusée (session expirée ?). Rechargez la page.'
    : status === 403 ? 'Action non autorisée.'
    : status === 404 ? 'Élément introuvable.'
    : `Erreur serveur (${status}).`;
  showToast('danger', message);
});

document.addEventListener('htmx:sendError', () => {
  showToast('danger', 'Serveur injoignable. Vérifiez la connexion.');
});

// Global progress bar, shown only for requests longer than 300 ms.
const PROGRESS_DELAY_MS = 300;
let pendingRequests = 0;
let progressTimer = null;

document.addEventListener('htmx:beforeRequest', () => {
  pendingRequests += 1;
  if (pendingRequests === 1) {
    progressTimer = setTimeout(
      () => document.documentElement.classList.add('htmx-loading'), PROGRESS_DELAY_MS);
  }
});

document.addEventListener('htmx:afterRequest', () => {
  pendingRequests = Math.max(0, pendingRequests - 1);
  if (pendingRequests === 0) {
    clearTimeout(progressTimer);
    document.documentElement.classList.remove('htmx-loading');
  }
});

// Upload progress for multipart forms containing a [data-upload-progress] bar.
document.addEventListener('htmx:xhr:progress', e => {
  const form = e.target.closest && e.target.closest('form');
  const bar = form && form.querySelector('[data-upload-progress]');
  if (!bar || !e.detail.lengthComputable) return;
  const pct = Math.round((e.detail.loaded / e.detail.total) * 100);
  bar.classList.remove('d-none');
  bar.setAttribute('aria-valuenow', pct);
  bar.firstElementChild.style.width = `${pct}%`;
  bar.firstElementChild.textContent = pct < 100 ? `${pct} %` : 'Traitement…';
});

// Keep the keyboard focus across a content swap: htmx only restores it for
// elements with an id, filter fields usually only have a name.
let focusedField = null;

document.addEventListener('htmx:beforeSwap', () => {
  const el = document.activeElement;
  focusedField = el && el.name && el.form
    ? { name: el.name, start: el.selectionStart, end: el.selectionEnd }
    : null;
});

document.addEventListener('htmx:afterSettle', () => {
  if (!focusedField || (document.activeElement && document.activeElement !== document.body)) return;
  const el = document.querySelector(`#page-content [name="${CSS.escape(focusedField.name)}"]`);
  if (!el) return;
  el.focus({ preventScroll: true });
  if (typeof focusedField.start === 'number' && el.setSelectionRange) {
    try { el.setSelectionRange(focusedField.start, focusedField.end); } catch (_) { /* not a text field */ }
  }
  focusedField = null;
});

// Live balance indicator on entry form
document.addEventListener('htmx:afterSettle', updateBalance);
document.addEventListener('input', updateBalance);

function updateBalance() {
  const indicator = document.getElementById('balance-indicator');
  if (!indicator) return;
  let debit = 0, credit = 0;
  document.querySelectorAll('input[name="debit[]"]').forEach(i => debit += parseFloat(i.value) || 0);
  document.querySelectorAll('input[name="credit[]"]').forEach(i => credit += parseFloat(i.value) || 0);
  const diff = Math.abs(debit - credit);
  if (diff < 0.001) {
    indicator.textContent = `✓ Équilibré (${debit.toFixed(2)} €)`;
    indicator.className = 'ms-auto text-success small';
  } else {
    indicator.textContent = `Déséquilibre : ${diff.toFixed(2)} €`;
    indicator.className = 'ms-auto text-danger small';
  }
}

// Auto-uppercase journal code inputs
document.addEventListener('input', e => {
  if (e.target.name === 'code' && e.target.closest('form')) {
    const pos = e.target.selectionStart;
    e.target.value = e.target.value.toUpperCase();
    e.target.setSelectionRange(pos, pos);
  }
});
