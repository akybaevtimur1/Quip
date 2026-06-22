import { describe, expect, it } from "vitest";
import { captionedDownloadUrl } from "./api";

// Bug: after changing the hook font (or any caption edit), the "With captions" download
// served the previous baked render (old/default font) because the editor never invalidates
// `bakedUrl` on edit. The captioned download must NOT trust a baked render once there are
// un-rendered (dirty) edits — it must fall back to the always-fresh on-demand endpoint.
describe("captionedDownloadUrl", () => {
  const base = "https://worker.example";
  const jobId = "job1";
  const clipId = "clip_01";
  const onDemand = `${base}/jobs/${jobId}/clips/${clipId}/export/captioned.mp4`;

  it("uses the baked render when not dirty (fast path matches edit-state)", () => {
    const baked = "https://cdn.quip.ink/job1/clip_01_captioned.mp4?v=3";
    expect(captionedDownloadUrl(base, jobId, clipId, baked, false)).toBe(baked);
  });

  it("falls back to the fresh on-demand render when dirty (THE BUG)", () => {
    // A stale baked render from a previous font is present, but the user has since edited.
    const staleBaked = "https://cdn.quip.ink/job1/clip_01_captioned.mp4?v=3";
    expect(captionedDownloadUrl(base, jobId, clipId, staleBaked, true)).toBe(onDemand);
  });

  it("uses on-demand when there is no baked render yet", () => {
    expect(captionedDownloadUrl(base, jobId, clipId, null, false)).toBe(onDemand);
  });
});
