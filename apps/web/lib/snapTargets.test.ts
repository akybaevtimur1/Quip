import { describe, expect, it } from "vitest";
import { buildTargets } from "./snapTargets";

describe("buildTargets", () => {
  it("emits canvas centers + 4 edges with no other/safe", () => {
    const t = buildTargets(200, 400, null, null);
    expect(t).toContainEqual({ axis: "x", pos: 100, kind: "center" });
    expect(t).toContainEqual({ axis: "y", pos: 200, kind: "center" });
    expect(t).toContainEqual({ axis: "x", pos: 0, kind: "edge" });
    expect(t).toContainEqual({ axis: "x", pos: 200, kind: "edge" });
    expect(t).toContainEqual({ axis: "y", pos: 0, kind: "edge" });
    expect(t).toContainEqual({ axis: "y", pos: 400, kind: "edge" });
    expect(t.filter((x) => x.kind === "safe")).toEqual([]);
    expect(t.filter((x) => x.kind === "element")).toEqual([]);
  });
  it("adds safe-area lines", () => {
    const t = buildTargets(200, 400, null, { top: 40, bottom: 320, left: 10, right: 180 });
    expect(t).toContainEqual({ axis: "y", pos: 40, kind: "safe" });
    expect(t).toContainEqual({ axis: "y", pos: 320, kind: "safe" });
    expect(t).toContainEqual({ axis: "x", pos: 10, kind: "safe" });
    expect(t).toContainEqual({ axis: "x", pos: 180, kind: "safe" });
  });
  it("adds the other element's center/edges", () => {
    const t = buildTargets(200, 400, { left: 60, top: 100, width: 80, height: 40 }, null);
    expect(t).toContainEqual({ axis: "x", pos: 100, kind: "element" }); // center-x 60+40
    expect(t).toContainEqual({ axis: "x", pos: 60, kind: "element" });
    expect(t).toContainEqual({ axis: "x", pos: 140, kind: "element" });
    expect(t).toContainEqual({ axis: "y", pos: 120, kind: "element" }); // center-y 100+20
    expect(t).toContainEqual({ axis: "y", pos: 100, kind: "element" });
    expect(t).toContainEqual({ axis: "y", pos: 140, kind: "element" });
  });
});
