/** Presentation helpers only — never derives or invents domain values. */

export function formatInr(amount: number): string {
  return `₹${new Intl.NumberFormat('en-IN').format(amount)}`;
}

export function formatMinutes(minutes: number): string {
  if (minutes === 0) return 'No delay';
  const hours = Math.floor(Math.abs(minutes) / 60);
  const rest = Math.abs(minutes) % 60;
  const sign = minutes < 0 ? '−' : '+';
  if (hours === 0) return `${sign}${rest}m`;
  return rest === 0 ? `${sign}${hours}h` : `${sign}${hours}h ${rest}m`;
}

export function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return `${date.toISOString().slice(0, 10)} · ${date.toISOString().slice(11, 16)}Z`;
}