// Единственный источник API-типов — сгенерированный контракт @clipflow/shared
// (из app/models.py). Здесь только реэкспорт + UI-состояния.
export type { Clip, ClipOut, ClipType, Job, JobStatus, Metrics, SourceKind, Word } from "@clipflow/shared";
export type {
  CaptionPreset,
  CaptionStyle,
  CaptionTrack,
  ClipEdit,
  CropOverride,
  HighlightStyle,
  SourceInterval,
} from "@clipflow/shared";

// UI state-машина страницы.
export type View =
  | { state: "idle" }
  | { state: "submitting" }
  | { state: "tracking" }
  | { state: "done" }
  | { state: "error"; message: string };
