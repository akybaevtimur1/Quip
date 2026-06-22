import { describe, expect, it } from "vitest";
import { clipRange, mmss, usd } from "./format";

describe("mmss", () => {
  it("formats whole seconds as m:ss", () => {
    expect(mmss(0)).toBe("0:00");
    expect(mmss(5)).toBe("0:05");
    expect(mmss(65)).toBe("1:05");
    expect(mmss(600)).toBe("10:00");
  });

  it("rolls over to h:mm:ss past an hour", () => {
    expect(mmss(3600)).toBe("1:00:00");
    expect(mmss(3661)).toBe("1:01:01");
  });

  it("rounds float seconds cleanly — no FP noise (regression: 3:21.751000000000005)", () => {
    // Elapsed time arrives as a float; the old inline math leaked `21.751000000000005`.
    expect(mmss(201.751000000000005)).toBe("3:22");
    expect(mmss(136.251000000000005)).toBe("2:16");
    expect(mmss(5.4)).toBe("0:05");
    // No fractional/garbage characters in the output, ever.
    expect(mmss(201.751000000000005)).not.toContain(".");
  });

  it("guards against NaN / non-finite from the wire", () => {
    expect(mmss(Number.NaN)).toBe("0:00");
    expect(mmss(Number.POSITIVE_INFINITY)).toBe("0:00");
    expect(mmss(-5)).toBe("0:00");
  });
});

describe("clipRange", () => {
  it("renders a source-coordinate range", () => {
    expect(clipRange(12, 45)).toBe("0:12–0:45");
  });
});

describe("usd", () => {
  it("formats dollars and guards NaN", () => {
    expect(usd(0.16)).toBe("$0.16");
    expect(usd(Number.NaN)).toBe("$0.00");
  });
});
