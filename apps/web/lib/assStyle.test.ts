import { describe, expect, it } from "vitest";
import {
  buildDefaultStyleLine,
  buildHookStyleLine,
  patchAssStyles,
  resolveFontForText,
} from "./assStyle";
import type { CaptionStyle, HookOverlay } from "@/lib/types";

// Mirror of services/worker/tests/unit/test_captions_v2.py resolve_font_for_text cases —
// the TS swap MUST match the Python one so libass preview == ffmpeg baked render (WYSIWYG).
const KAZAKH = "Сәлем! Қазақша мәтін: ғ қ ң ө ұ ү һ і";

// Each display slot → its Cyrillic-capable look-match (mirror LOOK_MATCH_FOR_CYRILLIC).
const LOOK_MATCH: Record<string, string> = {
  Unbounded: "Rubik Black",
  "Russo One": "Play",
  Anton: "Oswald Heavy",
  "Bebas Neue": "Oswald",
  "Archivo Black": "Inter",
  "Luckiest Guy": "Nunito Black",
  Poppins: "Rubik",
};

describe("resolveFontForText (mirror of captions_v2.resolve_font_for_text)", () => {
  it("every display slot swaps to its look-match on Russian (look applies to all Cyrillic)", () => {
    for (const [orig, look] of Object.entries(LOOK_MATCH)) {
      expect(resolveFontForText(orig, "Привет мир")).toBe(look);
    }
  });
  it("every display slot swaps to its look-match on Kazakh", () => {
    for (const [orig, look] of Object.entries(LOOK_MATCH)) {
      expect(resolveFontForText(orig, "Қазақша мәтін")).toBe(look);
    }
  });
  it("Latin-only font + Latin → unchanged (no Cyrillic → no swap)", () => {
    expect(resolveFontForText("Anton", "Hello world")).toBe("Anton");
    expect(resolveFontForText("Poppins", "Hello")).toBe("Poppins");
  });
  it("Unbounded (hook default) → Rubik Black (the most important slot)", () => {
    expect(resolveFontForText("Unbounded", "Қазақша")).toBe("Rubik Black");
    expect(resolveFontForText("Unbounded", KAZAKH)).toBe("Rubik Black");
    expect(resolveFontForText("Unbounded", "Привет мир")).toBe("Rubik Black");
  });
  it("Russo One (preset u) → Play", () => {
    expect(resolveFontForText("Russo One", "Қазақ мәтіні")).toBe("Play");
    expect(resolveFontForText("Russo One", "Привет")).toBe("Play");
  });
  it("Montserrat + Kazakh → unchanged (covers all 18, not in look-match)", () => {
    expect(resolveFontForText("Montserrat", KAZAKH)).toBe("Montserrat");
  });
});

describe("style-line font swap + bold flag follow the resolved font", () => {
  it("Default line swaps Russo One → Play (bold 0, single-weight) for Kazakh", () => {
    const style = { font: "Russo One", size: 90 } as CaptionStyle;
    const line = buildDefaultStyleLine(style, null, 1080, KAZAKH);
    const fields = line.replace("Style: ", "").split(",");
    expect(fields[1]).toBe("Play"); // Fontname
    expect(fields[7]).toBe("0"); // Bold: Play is a single-weight look-match → 0
  });
  it("Default line swaps Russo One → Play for Russian too (look applies to all Cyrillic)", () => {
    const style = { font: "Russo One", size: 90 } as CaptionStyle;
    const fields = buildDefaultStyleLine(style, null, 1080, "Привет")
      .replace("Style: ", "")
      .split(",");
    expect(fields[1]).toBe("Play");
    expect(fields[7]).toBe("0");
  });
  it("Default line keeps Russo One (bold 0) for pure Latin", () => {
    const style = { font: "Russo One", size: 90 } as CaptionStyle;
    const fields = buildDefaultStyleLine(style, null, 1080, "Hello")
      .replace("Style: ", "")
      .split(",");
    expect(fields[1]).toBe("Russo One");
    expect(fields[7]).toBe("0");
  });
  it("Hook line swaps Unbounded → Rubik Black using hook.text for Kazakh", () => {
    const hook = { font: "Unbounded", text: "Сәлем достар!" } as HookOverlay;
    const fields = buildHookStyleLine(hook, 1080).replace("Style: ", "").split(",");
    expect(fields[1]).toBe("Rubik Black");
    expect(fields[7]).toBe("0"); // single-weight look-match → 0
  });
});

describe("patchAssStyles end-to-end font swap", () => {
  const ass = [
    "[Script Info]",
    "PlayResX: 1080",
    "PlayResY: 1920",
    "[V4+ Styles]",
    "Style: Default,Russo One,90,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,6,2,2,40,40,260,1",
    "Style: Hook,Unbounded,66,&H00FFFFFF,&H00FFFFFF,&H00FF5A3D,&H00000000,0,0,0,0,100,100,0,0,3,6,0,8,60,60,150,1",
    "[Events]",
    "Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,,{\\k40}Қазақша",
    "Dialogue: 0,0:00:00.00,0:00:02.00,Hook,,0,0,,СӘЛЕМ",
  ].join("\n");

  it("rewrites Default→Play and Hook→Rubik Black when text is Kazakh", () => {
    const style = { font: "Russo One", size: 90 } as CaptionStyle;
    const hook = { font: "Unbounded", text: "Сәлем достар!", size: 66 } as HookOverlay;
    const out = patchAssStyles(ass, style, null, hook);
    const defaultLine = out.split("\n").find((l) => l.startsWith("Style: Default,"))!;
    const hookLine = out.split("\n").find((l) => l.startsWith("Style: Hook,"))!;
    expect(defaultLine.split(",")[1]).toBe("Play");
    expect(hookLine.split(",")[1]).toBe("Rubik Black");
  });
});
