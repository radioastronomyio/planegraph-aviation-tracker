export function formatDuration(startedAt: string, endedAt: string | null): string {
  if (!endedAt) return "In progress";
  const secs = Math.round((new Date(endedAt).getTime() - new Date(startedAt).getTime()) / 1000);
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}
