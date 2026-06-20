import { describe, expect, it } from "vitest";
import { resolveShortcut } from "./editorShortcuts";

const ev = (key: string, tag = "BODY", ce = false) => ({ key, target: { tagName: tag, isContentEditable: ce } });

describe("resolveShortcut", () => {
  it("space → playPause", () => expect(resolveShortcut(ev(" "))).toBe("playPause"));
  it("brackets → prev/next clip", () => { expect(resolveShortcut(ev("["))).toBe("prevClip"); expect(resolveShortcut(ev("]"))).toBe("nextClip"); });
  it("r → render", () => expect(resolveShortcut(ev("r"))).toBe("render"));
  it("Escape → closeOverlay", () => expect(resolveShortcut(ev("Escape"))).toBe("closeOverlay"));
  it("digits → tab index", () => expect(resolveShortcut(ev("3"))).toEqual({ tab: 3 }));
  it("ignores when typing in input", () => expect(resolveShortcut(ev(" ", "INPUT"))).toBeNull());
  it("ignores when contenteditable", () => expect(resolveShortcut(ev("r", "DIV", true))).toBeNull());
  it("unknown key → null", () => expect(resolveShortcut(ev("q"))).toBeNull());
});
