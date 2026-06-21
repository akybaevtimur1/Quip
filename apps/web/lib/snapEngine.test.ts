import { describe, expect, it } from "vitest";
import { computeSnap, type SnapTarget } from "./snapEngine";

const box = { left: 100, top: 100, width: 40, height: 20 }; // center-x=120, center-y=110

describe("computeSnap", () => {
  it("snaps center-x to a near vertical center target", () => {
    const t: SnapTarget[] = [{ axis: "x", pos: 124, kind: "center" }]; // 4px from center-x 120
    const r = computeSnap(box, t, 8);
    expect(r.left).toBe(104); // shifted by +4 so center-x lands on 124
    expect(r.guides).toEqual([{ axis: "x", pos: 124, kind: "center" }]);
  });
  it("ignores targets beyond threshold", () => {
    const r = computeSnap(box, [{ axis: "x", pos: 200, kind: "edge" }], 8);
    expect(r.left).toBe(100); expect(r.guides).toEqual([]);
  });
  it("picks the nearest target per axis", () => {
    const t: SnapTarget[] = [
      { axis: "x", pos: 126, kind: "edge" },   // 6px from center-x
      { axis: "x", pos: 122, kind: "center" }, // 2px from center-x — nearer
    ];
    const r = computeSnap(box, t, 8);
    expect(r.left).toBe(102); expect(r.guides).toEqual([{ axis: "x", pos: 122, kind: "center" }]);
  });
  it("snaps a box EDGE (not just center) when it is the nearest feature", () => {
    // left edge = 100; target at 103 (3px) is nearer than center-x→any
    const r = computeSnap(box, [{ axis: "x", pos: 103, kind: "safe" }], 8);
    expect(r.left).toBe(103); expect(r.guides[0]).toEqual({ axis: "x", pos: 103, kind: "safe" });
  });
  it("snaps both axes independently", () => {
    const t: SnapTarget[] = [{ axis: "x", pos: 120, kind: "center" }, { axis: "y", pos: 112, kind: "center" }];
    const r = computeSnap(box, t, 8);
    expect(r.left).toBe(100); // center-x already 120
    expect(r.top).toBe(102);  // center-y 110 → 112
    expect(r.guides.length).toBe(2);
  });
  it("empty targets → identity", () => {
    const r = computeSnap(box, [], 8);
    expect(r).toEqual({ left: 100, top: 100, guides: [] });
  });
});
