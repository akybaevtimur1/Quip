// Known video container extensions — used to accept a file the browser reported with an EMPTY
// MIME type. Some OS/browser combos hand back `type: ""` for perfectly valid containers
// (.mkv/.mov/.webm/.avi and friends); without this fallback the upload form silently rejected
// real videos ("couldn't select my video, no error"). Order/case-insensitive.
const VIDEO_EXTENSIONS = [
  "mp4", "m4v", "mov", "qt", "webm", "mkv", "avi", "wmv", "flv",
  "mpg", "mpeg", "ts", "mts", "m2ts", "3gp", "3g2", "ogv",
] as const;

const VIDEO_EXT_RE = new RegExp(`\\.(${VIDEO_EXTENSIONS.join("|")})$`, "i");

/** True if `file` should be accepted as a video upload.
 *
 * A real `video/*` MIME always passes. An EMPTY MIME passes only when the filename carries a
 * known video extension (browsers leave `type` blank for some containers). A non-empty,
 * non-video MIME (image/png, application/pdf, …) is always rejected.
 */
export function isAcceptedVideoFile(name: string, type: string): boolean {
  if (type.startsWith("video/")) return true;
  if (type === "") return VIDEO_EXT_RE.test(name);
  return false;
}
