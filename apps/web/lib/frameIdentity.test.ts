import { describe, expect, it } from "vitest";
import { frameEqual, stableFrame } from "./frameIdentity";

const f = (cx: number) => ({ mode: "fill" as const, cx, cxB: 0.7 });

describe("frameIdentity", () => {
  it("equal when fields match", () => expect(frameEqual(f(0.5), f(0.5))).toBe(true));
  it("not equal when cx differs", () => expect(frameEqual(f(0.5), f(0.51))).toBe(false));
  it("null handling", () => { expect(frameEqual(null, null)).toBe(true); expect(frameEqual(null, f(0.5))).toBe(false); });
  it("stableFrame returns prev ref when equal", () => { const p = f(0.5); expect(stableFrame(p, f(0.5))).toBe(p); });
  it("stableFrame returns next when changed", () => { const n = f(0.6); expect(stableFrame(f(0.5), n)).toBe(n); });
});
