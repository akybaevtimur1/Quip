/** Секунды → `M:SS`. */
export function mmss(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, "0")}`;
}

/** Диапазон клипа в координатах источника, `M:SS–M:SS`. */
export function clipRange(start: number, end: number): string {
  return `${mmss(start)}–${mmss(end)}`;
}

/** Доллары: `$0.16`. */
export function usd(n: number): string {
  return `$${n.toFixed(2)}`;
}
