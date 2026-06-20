import type { FrameState } from "../components/editor/PreviewPlayer";

export function frameEqual(a: FrameState | null, b: FrameState | null): boolean {
  if (a === b) return true;
  if (!a || !b) return false;
  return a.mode === b.mode && a.cx === b.cx && a.cxB === b.cxB;
}

export function stableFrame(prev: FrameState | null, next: FrameState | null): FrameState | null {
  return frameEqual(prev, next) ? prev : next;
}
