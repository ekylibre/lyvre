// Jobs suivis à l'écran (composant JobStatus) : leur notification de fin ne s'affiche pas en
// message, le résultat étant déjà visible sur la page.
const watched = new Map<number, number>();

export function watchJob(jobId: number): () => void {
  watched.set(jobId, (watched.get(jobId) ?? 0) + 1);
  return () => {
    const count = (watched.get(jobId) ?? 1) - 1;
    if (count > 0) watched.set(jobId, count);
    else watched.delete(jobId);
  };
}

export function isWatchedJob(jobId: number): boolean {
  return watched.has(jobId);
}
