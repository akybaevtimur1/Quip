import { describe, expect, it } from "vitest";
import {
  captionedDownloadUrl,
  clipCaptionedExportUrl,
  clipCleanExportUrl,
  clipSrtUrl,
} from "./api";

const BASE = "https://worker.example";
const JOB = "job_123";
const CLIP = "clip_abc";

describe("per-clip export URL builders", () => {
  it("builds the on-demand clean MP4 endpoint", () => {
    expect(clipCleanExportUrl(BASE, JOB, CLIP)).toBe(
      "https://worker.example/jobs/job_123/clips/clip_abc/export/clean.mp4",
    );
  });

  it("builds the SRT endpoint", () => {
    expect(clipSrtUrl(BASE, JOB, CLIP)).toBe(
      "https://worker.example/jobs/job_123/clips/clip_abc/export.srt",
    );
  });

  it("builds the on-demand captioned MP4 endpoint", () => {
    expect(clipCaptionedExportUrl(BASE, JOB, CLIP)).toBe(
      "https://worker.example/jobs/job_123/clips/clip_abc/export/captioned.mp4",
    );
  });

  it("works with an empty base (relative worker path)", () => {
    expect(clipSrtUrl("", JOB, CLIP)).toBe("/jobs/job_123/clips/clip_abc/export.srt");
  });
});

describe("captionedDownloadUrl", () => {
  it("uses the baked CDN render when present and not dirty (fast path)", () => {
    const baked = "https://cdn.example/renders/clip_abc.mp4";
    expect(captionedDownloadUrl(BASE, JOB, CLIP, baked, false)).toBe(baked);
  });

  it("falls back to on-demand render when dirty (baked is stale)", () => {
    const baked = "https://cdn.example/renders/clip_abc.mp4";
    expect(captionedDownloadUrl(BASE, JOB, CLIP, baked, true)).toBe(
      clipCaptionedExportUrl(BASE, JOB, CLIP),
    );
  });

  it("falls back to on-demand render when there is no baked URL", () => {
    expect(captionedDownloadUrl(BASE, JOB, CLIP, null, false)).toBe(
      clipCaptionedExportUrl(BASE, JOB, CLIP),
    );
  });
});
