export function compact(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

export function duration(sec: number | null | undefined): string {
  if (!sec && sec !== 0) return "—";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function pct(n: number | null | undefined): string {
  return n === null || n === undefined ? "n/a" : `${n}%`;
}

// Normalize any ISO-ish date string to just YYYY-MM-DD (defends against the
// full-timestamp form Instagram returned, which overflowed the stat box).
export function dateOnly(s: string | null | undefined): string {
  if (!s) return "—";
  const m = /^(\d{4}-\d{2}-\d{2})/.exec(s);
  return m ? m[1] : s;
}
