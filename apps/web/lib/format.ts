/** Секунды → `M:SS` (или `H:MM:SS` от часа). NaN/неконечное → `0:00`. */
export function mmss(seconds: number): string {
  // Источник до 90 мин (90:00 читался как «минуты», а это 1:30:00) + защита от NaN с провода.
  const s = Number.isFinite(seconds) ? Math.max(0, Math.round(seconds)) : 0;
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = (s % 60).toString().padStart(2, "0");
  if (h > 0) return `${h}:${m.toString().padStart(2, "0")}:${sec}`;
  return `${m}:${sec}`;
}

/** Диапазон клипа в координатах источника, `M:SS–M:SS`. */
export function clipRange(start: number, end: number): string {
  return `${mmss(start)}–${mmss(end)}`;
}

/** Доллары: `$0.16`. NaN/неконечное → `$0.00` (значение с провода). */
export function usd(n: number): string {
  return `$${(Number.isFinite(n) ? n : 0).toFixed(2)}`;
}
