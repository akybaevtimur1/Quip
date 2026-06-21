import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readSafePref, readSnapPref, writeSafePref, writeSnapPref } from "./editorPrefs";

beforeEach(() => {
  const store: Record<string, string> = {};
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => (k in store ? store[k] : null),
    setItem: (k: string, v: string) => { store[k] = v; },
    removeItem: (k: string) => { delete store[k]; },
  });
});
afterEach(() => vi.unstubAllGlobals());

describe("editorPrefs", () => {
  it("snap defaults true, round-trips", () => {
    expect(readSnapPref()).toBe(true);
    writeSnapPref(false); expect(readSnapPref()).toBe(false);
  });
  it("safe defaults null, round-trips a platform and back to null", () => {
    expect(readSafePref()).toBe(null);
    writeSafePref("tiktok"); expect(readSafePref()).toBe("tiktok");
    writeSafePref(null); expect(readSafePref()).toBe(null);
  });
  it("ignores a corrupt safe value (returns null, no throw)", () => {
    localStorage.setItem("quip.editor.safe", "garbage");
    expect(readSafePref()).toBe(null);
  });
});
