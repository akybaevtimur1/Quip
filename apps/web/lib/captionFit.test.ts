import { describe, expect, it } from "vitest";
import { fitCaptionSize, wrapGreedy } from "./captionFit";

// Deterministic fake measurer: every character is `size` units wide (spaces included).
// width(text, size) = text.length * size. Lets us reason about wraps/fits exactly.
const measure = (text: string, size: number) => text.length * size;

describe("wrapGreedy", () => {
  it("keeps a line that fits on one line", () => {
    // "a b c" at size 1 = 5 units; frame 10 → fits on one line.
    expect(wrapGreedy("a b c", 1, 10, measure)).toEqual(["a b c"]);
  });

  it("breaks onto a new line when the next word would overflow", () => {
    // "aa bb cc" at size 1: "aa bb" = 5 (fits in 5), adding " cc" = 8 > 5 → wrap.
    expect(wrapGreedy("aa bb cc", 1, 5, measure)).toEqual(["aa bb", "cc"]);
  });

  it("puts a single over-wide word on its own (overflowing) line", () => {
    // "supercalifragilistic" is 20 units at size 1, frame 5 → its own line.
    expect(wrapGreedy("supercalifragilistic ok", 1, 5, measure)).toEqual([
      "supercalifragilistic",
      "ok",
    ]);
  });

  it("collapses internal whitespace and ignores empty input", () => {
    expect(wrapGreedy("   ", 1, 10, measure)).toEqual([]);
    expect(wrapGreedy("a   b", 1, 10, measure)).toEqual(["a b"]);
  });
});

describe("fitCaptionSize", () => {
  const base = {
    minSize: 10,
    maxSize: 100,
    lineHeight: 1.2,
    measure,
  };

  it("returns the max size when every page fits at the max", () => {
    // Page "a b" = 3 chars; at size 100 → 300 units. Frame 400 wide, tall enough.
    const size = fitCaptionSize({
      ...base,
      pages: ["a b"],
      frameWidth: 400,
      frameHeight: 1000,
    });
    expect(size).toBe(100);
  });

  it("shrinks so the widest page fits the frame width", () => {
    // Page "abcd" (4 chars) must fit width 200. Largest size with 4*size <= 200 → 50.
    const size = fitCaptionSize({
      ...base,
      pages: ["abcd"],
      frameWidth: 200,
      frameHeight: 100000,
    });
    expect(size).toBe(50);
  });

  it("shrinks so the tallest page fits the frame height", () => {
    // "aa bb": at size s, "aa"=2s, "aa bb"=5s. Frame width 30 lets each word fit
    // alone (2s<=30 ⇒ s<=15) but wraps the pair once 5s>30 (s>6) → 2 lines.
    // Height budget binds first: 2 lines * s * 1.2 <= 24 ⇒ s<=10 (size 11 → 26.4 > 24).
    const size = fitCaptionSize({
      ...base,
      pages: ["aa bb"],
      frameWidth: 30,
      frameHeight: 24,
      minSize: 1,
    });
    expect(size).toBe(10);
  });

  it("never goes below the min size, even if text can't truly fit", () => {
    const size = fitCaptionSize({
      ...base,
      pages: ["waytoolongword"],
      frameWidth: 1,
      frameHeight: 1,
      minSize: 12,
    });
    expect(size).toBe(12);
  });

  it("uses the WORST page across all pages (one stable size)", () => {
    // Short page would allow 100; long page "abcdefghij" (10 chars) caps width 200 → size 20.
    const size = fitCaptionSize({
      ...base,
      pages: ["a", "abcdefghij"],
      frameWidth: 200,
      frameHeight: 100000,
    });
    expect(size).toBe(20);
  });

  it("ignores empty/blank pages and returns max when nothing constrains", () => {
    const size = fitCaptionSize({
      ...base,
      pages: ["", "   "],
      frameWidth: 10,
      frameHeight: 10,
    });
    expect(size).toBe(100);
  });
});
