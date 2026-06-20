import { useEffect } from "react";
import { type EditorAction, resolveShortcut } from "@/lib/editorShortcuts";

export function useEditorShortcuts(dispatch: (a: EditorAction) => void) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const action = resolveShortcut({
        key: e.key,
        target: { tagName: target?.tagName, isContentEditable: target?.isContentEditable },
      });
      if (action === null) return;
      if (action === "playPause") e.preventDefault(); // stop page scroll on Space
      dispatch(action);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [dispatch]);
}
