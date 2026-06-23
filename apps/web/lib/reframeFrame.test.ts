import { describe, expect, it } from "vitest";
import type { CropOverride } from "@/lib/types";
import { pickActiveOverride } from "./reframeFrame";

const ov = (source_start: number, source_end: number, mode = "fit"): CropOverride => ({
  source_start,
  source_end,
  mode,
});

describe("pickActiveOverride", () => {
  it("a whole-clip override applies at any t inside it", () => {
    expect(pickActiveOverride([ov(0, 100)], 50)?.source_start).toBe(0);
    expect(pickActiveOverride([ov(0, 100)], 0)?.source_start).toBe(0);
  });

  it("a PER-SHOT override applies ONLY inside its range (not the whole clip)", () => {
    const overrides = [ov(10, 12, "fit")];
    expect(pickActiveOverride(overrides, 11)?.mode).toBe("fit"); // inside → applies
    expect(pickActiveOverride(overrides, 50)).toBeNull(); // outside → fall through to AI plan
    expect(pickActiveOverride(overrides, 9.99)).toBeNull(); // just before
    expect(pickActiveOverride(overrides, 12)).toBeNull(); // end exclusive
  });

  it("the last matching override wins (override-on-override)", () => {
    const r = pickActiveOverride([ov(0, 100, "fill"), ov(10, 20, "fit")], 15);
    expect(r?.mode).toBe("fit");
  });

  it("no overrides / none containing t → null", () => {
    expect(pickActiveOverride([], 5)).toBeNull();
    expect(pickActiveOverride([ov(10, 20)], 5)).toBeNull();
  });
});
