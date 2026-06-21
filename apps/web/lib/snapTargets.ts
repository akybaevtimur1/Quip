import type { SafeBox } from "./safeAreas";
import type { SnapTarget } from "./snapEngine";

export interface RectPx { left: number; top: number; width: number; height: number }

export function buildTargets(
  renderW: number,
  renderH: number,
  other: RectPx | null,
  safe: SafeBox | null,
): SnapTarget[] {
  const t: SnapTarget[] = [
    { axis: "x", pos: renderW / 2, kind: "center" },
    { axis: "y", pos: renderH / 2, kind: "center" },
    { axis: "x", pos: 0, kind: "edge" },
    { axis: "x", pos: renderW, kind: "edge" },
    { axis: "y", pos: 0, kind: "edge" },
    { axis: "y", pos: renderH, kind: "edge" },
  ];
  if (safe) {
    t.push({ axis: "x", pos: safe.left, kind: "safe" }, { axis: "x", pos: safe.right, kind: "safe" });
    t.push({ axis: "y", pos: safe.top, kind: "safe" }, { axis: "y", pos: safe.bottom, kind: "safe" });
  }
  if (other) {
    const cx = other.left + other.width / 2;
    const cy = other.top + other.height / 2;
    t.push({ axis: "x", pos: cx, kind: "element" }, { axis: "x", pos: other.left, kind: "element" }, { axis: "x", pos: other.left + other.width, kind: "element" });
    t.push({ axis: "y", pos: cy, kind: "element" }, { axis: "y", pos: other.top, kind: "element" }, { axis: "y", pos: other.top + other.height, kind: "element" });
  }
  return t;
}
