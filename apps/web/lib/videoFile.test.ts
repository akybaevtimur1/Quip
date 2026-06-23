import { describe, expect, it } from "vitest";
import { isAcceptedVideoFile } from "./videoFile";

describe("isAcceptedVideoFile", () => {
  it("accepts a normal video MIME regardless of extension", () => {
    expect(isAcceptedVideoFile("clip.mp4", "video/mp4")).toBe(true);
    expect(isAcceptedVideoFile("clip", "video/quicktime")).toBe(true);
  });

  it("accepts an EMPTY-MIME file when the extension is a known video container", () => {
    // The bug: some OS/browser combos report "" for .mkv/.mov/.webm/.avi → the old
    // `type.startsWith("video/")` check silently rejected real videos.
    expect(isAcceptedVideoFile("podcast.mkv", "")).toBe(true);
    expect(isAcceptedVideoFile("talk.MOV", "")).toBe(true);
    expect(isAcceptedVideoFile("stream.webm", "")).toBe(true);
    expect(isAcceptedVideoFile("old.avi", "")).toBe(true);
    expect(isAcceptedVideoFile("cam.m2ts", "")).toBe(true);
  });

  it("rejects an empty-MIME file with a non-video (or missing) extension", () => {
    expect(isAcceptedVideoFile("notes.txt", "")).toBe(false);
    expect(isAcceptedVideoFile("archive.zip", "")).toBe(false);
    expect(isAcceptedVideoFile("noext", "")).toBe(false);
  });

  it("rejects a file whose MIME is explicitly non-video", () => {
    expect(isAcceptedVideoFile("photo.mp4", "image/png")).toBe(false);
    expect(isAcceptedVideoFile("doc.pdf", "application/pdf")).toBe(false);
  });
});
