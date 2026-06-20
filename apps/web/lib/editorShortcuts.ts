export type EditorAction =
  | "playPause" | "prevClip" | "nextClip" | "render" | "closeOverlay" | { tab: number };

export function resolveShortcut(e: {
  key: string;
  target: { tagName?: string; isContentEditable?: boolean };
}): EditorAction | null {
  const t = e.target;
  if (t.isContentEditable || t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT") return null;
  switch (e.key) {
    case " ": return "playPause";
    case "[": return "prevClip";
    case "]": return "nextClip";
    case "r": case "R": return "render";
    case "Escape": return "closeOverlay";
    default:
      if (/^[1-6]$/.test(e.key)) return { tab: Number(e.key) };
      return null;
  }
}
