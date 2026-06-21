export type Axis = "x" | "y";
export type GuideKind = "center" | "edge" | "safe" | "element";
export interface DragBox { left: number; top: number; width: number; height: number }
export interface SnapTarget { axis: Axis; pos: number; kind: GuideKind }
export interface GuideLine { axis: Axis; pos: number; kind: GuideKind }
export interface SnapResult { left: number; top: number; guides: GuideLine[] }

export const SNAP_THRESHOLD_PX = 8;

function snapAxis(
  features: number[],
  targets: SnapTarget[],
  threshold: number,
): { delta: number; guide: GuideLine } | null {
  let best: { delta: number; guide: GuideLine; dist: number } | null = null;
  for (const t of targets) {
    for (const f of features) {
      const dist = Math.abs(f - t.pos);
      if (dist <= threshold && (best === null || dist < best.dist)) {
        best = { delta: t.pos - f, dist, guide: { axis: t.axis, pos: t.pos, kind: t.kind } };
      }
    }
  }
  return best ? { delta: best.delta, guide: best.guide } : null;
}

export function computeSnap(box: DragBox, targets: SnapTarget[], threshold: number): SnapResult {
  const guides: GuideLine[] = [];
  let { left, top } = box;
  const xs = snapAxis(
    [box.left, box.left + box.width / 2, box.left + box.width],
    targets.filter((t) => t.axis === "x"),
    threshold,
  );
  if (xs) { left += xs.delta; guides.push(xs.guide); }
  const ys = snapAxis(
    [box.top, box.top + box.height / 2, box.top + box.height],
    targets.filter((t) => t.axis === "y"),
    threshold,
  );
  if (ys) { top += ys.delta; guides.push(ys.guide); }
  return { left, top, guides };
}
