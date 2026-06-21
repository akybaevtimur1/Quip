import { describe, expect, it } from "vitest";
import { SAFE_AREAS, SAFE_PLATFORMS, safeBoxPx } from "./safeAreas";

describe("safeAreas", () => {
  it("has the three platforms", () => expect(SAFE_PLATFORMS).toEqual(["tiktok", "reels", "shorts"]));
  it("insets are fractions inside the frame (0<top<bottom<1, 0<left<right<1)", () => {
    for (const p of SAFE_PLATFORMS) {
      const s = SAFE_AREAS[p];
      expect(s.top).toBeGreaterThan(0); expect(s.top).toBeLessThan(s.bottom); expect(s.bottom).toBeLessThan(1);
      expect(s.left).toBeGreaterThan(0); expect(s.left).toBeLessThan(s.right); expect(s.right).toBeLessThan(1);
    }
  });
  it("safeBoxPx maps fractions to px", () => {
    expect(safeBoxPx({ top: 0.1, bottom: 0.8, left: 0.05, right: 0.9 }, 200, 400))
      .toEqual({ top: 40, bottom: 320, left: 10, right: 180 });
  });
});
