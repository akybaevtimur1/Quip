import { describe, expect, it } from "vitest";
import { DEFAULT_LOCALE, isLocale, LOCALES, resolveLocale } from "./locale";

describe("resolveLocale", () => {
  it("returns the locale unchanged for a supported value", () => {
    expect(resolveLocale("en")).toBe("en");
    expect(resolveLocale("ru")).toBe("ru");
  });

  it("falls back to the default for missing input (crawlers send no cookie)", () => {
    expect(resolveLocale(undefined)).toBe(DEFAULT_LOCALE);
    expect(resolveLocale(null)).toBe(DEFAULT_LOCALE);
    expect(resolveLocale("")).toBe(DEFAULT_LOCALE);
  });

  it("falls back to the default for unknown / unsupported values", () => {
    expect(resolveLocale("fr")).toBe(DEFAULT_LOCALE);
    expect(resolveLocale("EN")).toBe(DEFAULT_LOCALE); // case-sensitive on purpose
    expect(resolveLocale("en-US")).toBe(DEFAULT_LOCALE);
  });

  it("only ever returns a value from the supported set", () => {
    for (const candidate of ["en", "ru", "xx", undefined, null]) {
      expect(LOCALES).toContain(resolveLocale(candidate));
    }
  });
});

describe("isLocale", () => {
  it("accepts exactly the supported locales", () => {
    expect(isLocale("en")).toBe(true);
    expect(isLocale("ru")).toBe(true);
  });

  it("rejects everything else", () => {
    expect(isLocale("fr")).toBe(false);
    expect(isLocale("")).toBe(false);
    expect(isLocale(undefined)).toBe(false);
    expect(isLocale(42)).toBe(false);
  });
});
