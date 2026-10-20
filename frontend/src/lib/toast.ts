// Notifications : réutilise les toasts de la page (app/static/js/app.js),
// mêmes visuels que les messages flash et les réponses HTMX.

type Level = "success" | "danger" | "warning" | "info";

declare global {
  interface Window {
    showToast?: (level: Level, message: string) => void;
  }
}

export function toast(level: Level, message: string): void {
  if (window.showToast) window.showToast(level, message);
  else console.info(`[${level}] ${message}`);
}
