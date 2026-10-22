// Instances : bases comptables gérées par l'application (API /api/v1/instances, méta-base).
export const INSTANCES_KEY = ["instances"];

export interface Instance {
  id: number; slug: string; label: string; database: string; chart: string; chart_label: string; is_active: boolean;
  created_at: string | null; sqlite: boolean;
}

export interface Backup {
  filename: string; size_bytes: number; created_at: string | null; is_pre_restore: boolean; database_only: boolean; download_url: string;
}

export const BACKUP_ACCEPT = {
  "application/zip": [".zip"], "application/x-zip-compressed": [".zip"],
  "application/x-sqlite3": [".db", ".sqlite"], "application/octet-stream": [".db", ".sqlite", ".backup"],
};

/** Slug déduit du nom d'une sauvegarde (« pre-restore-asso-dupont-20261022-120000.zip » → « asso-dupont »). */
export function slugFromFilename(filename: string): string {
  return filename.replace(/^pre-restore-/i, "").replace(/\.(zip|db|sqlite|backup)$/i, "")
    .replace(/-\d{8}-\d{6}$/, "").toLowerCase();
}

export function labelFromSlug(slug: string): string {
  return slug.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function megabytes(bytes: number): string {
  return `${(bytes / 1024 / 1024).toFixed(1).replace(".", ",")} Mo`;
}
