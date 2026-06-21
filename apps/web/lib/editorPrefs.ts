import { SAFE_PLATFORMS, type SafePlatform } from "./safeAreas";

const SNAP_KEY = "quip.editor.snap";
const SAFE_KEY = "quip.editor.safe";

function safeLocalStorage(): Storage | null {
  try { return typeof localStorage !== "undefined" ? localStorage : null; } catch { return null; }
}

export function readSnapPref(): boolean {
  const ls = safeLocalStorage();
  return ls?.getItem(SNAP_KEY) === "off" ? false : true; // default true
}

export function writeSnapPref(v: boolean): void {
  safeLocalStorage()?.setItem(SNAP_KEY, v ? "on" : "off");
}

export function readSafePref(): SafePlatform | null {
  const v = safeLocalStorage()?.getItem(SAFE_KEY);
  return v && (SAFE_PLATFORMS as string[]).includes(v) ? (v as SafePlatform) : null;
}

export function writeSafePref(v: SafePlatform | null): void {
  const ls = safeLocalStorage();
  if (!ls) return;
  if (v) ls.setItem(SAFE_KEY, v); else ls.removeItem(SAFE_KEY);
}
