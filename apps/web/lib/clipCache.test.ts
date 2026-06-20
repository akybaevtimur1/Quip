import { describe, expect, it } from "vitest";
import { createClipCache } from "./clipCache";

describe("clipCache", () => {
  it("stores and reads", () => { const c = createClipCache<number>(2); c.set("a", 1); expect(c.get("a")).toBe(1); expect(c.has("a")).toBe(true); });
  it("evicts oldest beyond max", () => {
    const c = createClipCache<number>(2);
    c.set("a", 1); c.set("b", 2); c.set("c", 3);
    expect(c.has("a")).toBe(false); expect(c.has("b")).toBe(true); expect(c.has("c")).toBe(true); expect(c.size()).toBe(2);
  });
  it("re-set refreshes recency", () => {
    const c = createClipCache<number>(2);
    c.set("a", 1); c.set("b", 2); c.set("a", 1); c.set("c", 3);
    expect(c.has("a")).toBe(true); expect(c.has("b")).toBe(false);
  });
});
