import { describe, expect, it } from "vitest";
import { isConnectivityError } from "./connectionError";

// The bug this guards: a flaky connection used to look like a fatal "lost connection to the
// worker" failure and abandon a job that was still alive server-side. We must classify a
// connectivity blip (reconnect, keep the job) apart from a real HTTP/app error (surface it).
describe("isConnectivityError", () => {
  it("treats a fetch network failure (TypeError) as connectivity", () => {
    // fetch() rejects with a TypeError ("Failed to fetch") when the network drops.
    expect(isConnectivityError(new TypeError("Failed to fetch"), true)).toBe(true);
  });

  it("treats an aborted/timed-out request (AbortError) as connectivity", () => {
    // fetchWithTimeout aborts a stalled poll → DOMException name "AbortError".
    expect(isConnectivityError(new DOMException("Aborted", "AbortError"), true)).toBe(true);
  });

  it("treats a spec TimeoutError as connectivity", () => {
    expect(isConnectivityError(new DOMException("Timed out", "TimeoutError"), true)).toBe(true);
  });

  it("treats ANY error as connectivity when the browser is offline", () => {
    // No network → the job is alive but unreachable; reconnect, don't fail — whatever threw.
    expect(isConnectivityError(new Error("getJob failed: 500"), false)).toBe(true);
    expect(isConnectivityError(new TypeError("Failed to fetch"), false)).toBe(true);
  });

  it("treats a real HTTP/app error (online) as a genuine failure, not connectivity", () => {
    expect(isConnectivityError(new Error("getJob failed: 500"), true)).toBe(false);
    expect(isConnectivityError(new Error("getJob failed: 404"), true)).toBe(false);
  });

  it("treats an unknown non-error throw (online) as a genuine failure", () => {
    expect(isConnectivityError("boom", true)).toBe(false);
    expect(isConnectivityError(null, true)).toBe(false);
    expect(isConnectivityError(undefined, true)).toBe(false);
  });
});
