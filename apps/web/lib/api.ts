import { createSupabaseBrowserClient } from "./supabase/client";
import { isSupabaseConfigured } from "./supabase/config";
import type {
  CaptionPreset,
  CaptionTrack,
  ChaptersData,
  ClipEdit,
  Job,
  TimelineData,
  Word,
} from "./types";

// База воркера: реальный worker через env, иначе встроенный мок (/api/mock).
const BASE = process.env.NEXT_PUBLIC_WORKER_URL ?? "/api/mock";

/** Заголовок авторизации для воркера: текущий Supabase access_token (когда auth настроен).
 *  Воркер валидирует JWT (JWKS проекта) и достаёт user_id. Без auth → пустой объект (dev). */
async function authHeaders(): Promise<Record<string, string>> {
  if (!isSupabaseConfigured) return {};
  try {
    const { data } = await createSupabaseBrowserClient().auth.getSession();
    const token = data.session?.access_token;
    return token ? { Authorization: `Bearer ${token}` } : {};
  } catch {
    return {};
  }
}

export type CreateJobInput = {
  source_type: "youtube";
  source_ref: string;
  max_clips?: number;
};

export interface UsageInfo {
  plan: string;
  plan_name: string;
  monthly_videos: number; // план: видео/мес (free=2)
  monthly_minutes: number; // = monthly_videos × 60 (free=120)
  used_minutes: number; // израсходовано в этом месяце (дробно)
  remaining_minutes: number; // осталось в месячном пуле (без PAYG)
  remaining_videos: number; // = remaining_minutes / 60 (напр. 8.7)
  payg_videos: number; // не сгорающий баланс (видео)
  payg_minutes: number; // = payg_videos × 60
}

export async function createJob(input: CreateJobInput): Promise<{ id: string }> {
  const res = await fetch(`${BASE}/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify(input),
  });
  await throwOnAuthOrQuota(res);
  if (!res.ok) throw new Error(`createJob failed: ${res.status}`);
  return res.json();
}

/** 401/402 от воркера → понятная ошибка (серверная причина квоты сохраняется). */
async function throwOnAuthOrQuota(res: Response): Promise<void> {
  if (res.status === 401) throw new Error("Sign in to create clips.");
  if (res.status === 402) {
    const body = (await res.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? "Monthly limit reached. Upgrade your plan on the pricing page.");
  }
}

export async function createUploadJob(
  file: File,
  maxClips?: number,
  onProgress?: (pct: number) => void,
  signal?: AbortSignal,
): Promise<{ id: string }> {
  const form = new FormData();
  form.append("file", file);
  if (maxClips != null) form.append("max_clips", String(maxClips));
  const headers = await authHeaders();

  // XMLHttpRequest (not fetch) so we get real upload-progress events — a big file
  // from a laptop can take a while, and a dead-looking screen reads as "broken".
  // Don't set Content-Type — the browser adds the multipart boundary itself.
  return new Promise<{ id: string }>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${BASE}/jobs/upload`);
    for (const [k, v] of Object.entries(headers)) xhr.setRequestHeader(k, v);

    // Abort support: leaving the page / "New project" / a second upload must CANCEL this
    // in-flight upload — otherwise the orphaned XHR still creates a job on the worker and
    // its late resolve stomps the UI (duplicate jobs, progress jumping). See dashboard.
    if (signal) {
      if (signal.aborted) {
        xhr.abort();
        return reject(new DOMException("Upload aborted", "AbortError"));
      }
      signal.addEventListener(
        "abort",
        () => {
          xhr.abort();
          reject(new DOMException("Upload aborted", "AbortError"));
        },
        { once: true },
      );
    }

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status === 401) return reject(new Error("Sign in to create clips."));
      if (xhr.status === 402) {
        let detail: string | undefined;
        try {
          detail = (JSON.parse(xhr.responseText) as { detail?: string }).detail;
        } catch {
          detail = undefined;
        }
        return reject(
          new Error(detail ?? "Monthly limit reached. Upgrade your plan on the pricing page."),
        );
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        return reject(new Error(`createUploadJob failed: ${xhr.status}`));
      }
      try {
        resolve(JSON.parse(xhr.responseText) as { id: string });
      } catch {
        reject(new Error("createUploadJob: invalid server response"));
      }
    };
    xhr.onerror = () => reject(new Error("Upload failed — check your connection and try again"));
    xhr.send(form);
  });
}

/** Живой расход (план + остаток кредитов) для UsageMeter. Бросает при недоступности —
 *  UsageMeter откатывается на дефолт free (dual-mode без воркера/auth). */
export async function getUsage(): Promise<UsageInfo> {
  const res = await fetch(`${BASE}/usage`, { cache: "no-store", headers: await authHeaders() });
  if (!res.ok) throw new Error(`getUsage failed: ${res.status}`);
  return res.json();
}

/** fetch с таймаутом: висящий ответ (TCP открыт, воркер молчит) иначе НИКОГДА не реджектит →
 *  поллинг useJob тихо стопорится, MAX_FAILS не растёт, юзер на «tracking» навсегда.
 *  Таймаут → AbortError → throw → засчитывается как сбой опроса. */
async function fetchWithTimeout(input: string, init: RequestInit = {}, ms = 15000): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  try {
    return await fetch(input, { ...init, signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
}

export async function getJob(id: string): Promise<Job> {
  const res = await fetchWithTimeout(`${BASE}/jobs/${id}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`getJob failed: ${res.status}`);
  return res.json();
}

export async function getTimeline(jobId: string): Promise<TimelineData> {
  const res = await fetch(`${BASE}/jobs/${jobId}/timeline`, { cache: "no-store" });
  if (!res.ok) throw new Error(`getTimeline failed: ${res.status}`);
  return res.json();
}

export async function getChapters(jobId: string, retry = false): Promise<ChaptersData> {
  // AI-карта видео (главы). Первый вызов стартует генерацию (status=pending) → поллить.
  // retry=true перезапускает генерацию, если предыдущая упала (квота Gemini free-tier).
  const url = `${BASE}/jobs/${jobId}/chapters${retry ? "?retry=true" : ""}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`getChapters failed: ${res.status}`);
  return res.json();
}

export async function setCropOverride(
  jobId: string,
  clipId: string,
  version: number,
  body: {
    source_start: number;
    source_end: number;
    mode: "fill" | "fit" | "split" | "auto";
    center?: number | null;
    center_b?: number | null;
  },
): Promise<ClipEdit> {
  const res = await fetch(`${BASE}/jobs/${jobId}/clips/${clipId}/edit/crop`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ version, ...body }),
  });
  if (res.status === 409) throw new Error("Edit conflict — reload and retry");
  if (!res.ok) throw new Error(`setCropOverride failed: ${res.status}`);
  return res.json();
}

export type Aspect = "9:16" | "1:1" | "4:5" | "16:9";

export async function setClipAspect(
  jobId: string,
  clipId: string,
  version: number,
  aspect: Aspect,
): Promise<ClipEdit> {
  // T5: сменить соотношение сторон клипа (выход + reframe-кроп; кадровая сетка не трогается).
  const res = await fetch(`${BASE}/jobs/${jobId}/clips/${clipId}/edit/aspect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ version, aspect }),
  });
  if (res.status === 409) throw new Error("Edit conflict — reload and retry");
  if (!res.ok) throw new Error(`setClipAspect failed: ${res.status}`);
  return res.json();
}

export async function setClipInterval(
  jobId: string,
  clipId: string,
  version: number,
  sourceStart: number,
  sourceEnd: number,
): Promise<ClipEdit> {
  const res = await fetch(`${BASE}/jobs/${jobId}/clips/${clipId}/edit/set-interval`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ version, source_start: sourceStart, source_end: sourceEnd }),
  });
  if (res.status === 409) throw new Error("Edit conflict — reload and retry");
  if (!res.ok) throw new Error(`setClipInterval failed: ${res.status}`);
  return res.json();
}

export async function getClipAss(jobId: string, clipId: string): Promise<string> {
  // ASS субтитров текущего edit-state — для libass.wasm превью (тот же ASS, что жжёт ffmpeg).
  const res = await fetch(`${BASE}/jobs/${jobId}/clips/${clipId}/ass`, { cache: "no-store" });
  if (!res.ok) throw new Error(`getClipAss failed: ${res.status}`);
  return res.text();
}

export interface ReframeRegion {
  t0: number;
  t1: number;
  mode: string;
  points: { t: number; mode?: string; cx: number | null }[];
  points_b?: { t: number; mode?: string; cx: number | null }[];
}

export async function getClipReframe(
  jobId: string,
  clipId: string,
): Promise<{ regions: ReframeRegion[] }> {
  // D2: reframe-план (fit/fill/split + центры) от ЕДИНОГО frame-accurate пути (как у рендера).
  // Заменяет прямой fetch media/<job>/reframe_<clip>.json — тот 404-ил на облаке (файл только
  // на scratch batch-контейнера) → превью откатывалось в центр-кроп ≠ рендер.
  const res = await fetch(`${BASE}/jobs/${jobId}/clips/${clipId}/reframe`, { cache: "no-store" });
  if (!res.ok) throw new Error(`getClipReframe failed: ${res.status}`);
  return res.json();
}

export async function getClipEdit(jobId: string, clipId: string): Promise<ClipEdit> {
  const res = await fetch(`${BASE}/jobs/${jobId}/clips/${clipId}/edit`, { cache: "no-store" });
  if (!res.ok) throw new Error(`getClipEdit failed: ${res.status}`);
  return res.json();
}

export async function getClipAnalysis(
  jobId: string,
  clipId: string,
): Promise<{ intervals: { source_start: number; source_end: number }[]; words: Word[] }> {
  const res = await fetch(`${BASE}/jobs/${jobId}/clips/${clipId}/analysis`, { cache: "no-store" });
  if (!res.ok) throw new Error(`getClipAnalysis failed: ${res.status}`);
  return res.json();
}

export async function trimClip(
  jobId: string,
  clipId: string,
  version: number,
  wordIndices: number[],
): Promise<ClipEdit> {
  const res = await fetch(`${BASE}/jobs/${jobId}/clips/${clipId}/edit/trim`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ version, word_indices: wordIndices }),
  });
  if (res.status === 409) throw new Error("Edit conflict — reload and retry");
  if (!res.ok) throw new Error(`trimClip failed: ${res.status}`);
  return res.json();
}

export async function extendClip(
  jobId: string,
  clipId: string,
  version: number,
  edge: "start" | "end",
  newValue: number,
): Promise<ClipEdit> {
  const res = await fetch(`${BASE}/jobs/${jobId}/clips/${clipId}/edit/extend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ version, edge, new_value: newValue }),
  });
  if (res.status === 409) throw new Error("Edit conflict — reload and retry");
  if (!res.ok) throw new Error(`extendClip failed: ${res.status}`);
  return res.json();
}

export async function startRenderClip(jobId: string, clipId: string): Promise<{ status: string }> {
  const res = await fetch(`${BASE}/jobs/${jobId}/clips/${clipId}/render`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  if (!res.ok) throw new Error(`startRenderClip failed: ${res.status}`);
  return res.json();
}

export async function getRenderStatus(
  jobId: string,
  clipId: string,
): Promise<{ status: string; video_url: string | null; error: string | null }> {
  const res = await fetch(`${BASE}/jobs/${jobId}/clips/${clipId}/render`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`getRenderStatus failed: ${res.status}`);
  return res.json();
}

export async function patchClipEdit(
  jobId: string,
  clipId: string,
  version: number,
  captions: CaptionTrack,
): Promise<ClipEdit> {
  const res = await fetch(`${BASE}/jobs/${jobId}/clips/${clipId}/edit`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ version, captions }),
  });
  if (res.status === 409) throw new Error("Edit conflict — reload and retry");
  if (!res.ok) throw new Error(`patchClipEdit failed: ${res.status}`);
  return res.json();
}

/**
 * Best-effort persist of caption edits when the page is going away (pagehide /
 * visibilitychange-hidden / unmount). Uses `keepalive` so the request outlives the
 * document — a normal fetch would be cancelled on unload, silently losing edits.
 * Fire-and-forget: no body parsing, swallow errors (the page is leaving). This is
 * the durability backstop so a long edit session is never lost on navigate/close.
 */
export function patchClipEditKeepalive(
  jobId: string,
  clipId: string,
  version: number,
  captions: CaptionTrack,
): void {
  try {
    void fetch(`${BASE}/jobs/${jobId}/clips/${clipId}/edit`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ version, captions }),
      keepalive: true,
    });
  } catch {
    /* page is leaving — nothing we can do */
  }
}

export async function getPresets(): Promise<CaptionPreset[]> {
  const res = await fetch(`${BASE}/presets`, { cache: "no-store" });
  if (!res.ok) throw new Error(`getPresets failed: ${res.status}`);
  return res.json();
}

export async function applyPreset(
  jobId: string,
  clipId: string,
  version: number,
  presetId: string,
): Promise<ClipEdit> {
  const res = await fetch(`${BASE}/jobs/${jobId}/clips/${clipId}/apply-preset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ version, preset_id: presetId }),
  });
  if (res.status === 409) throw new Error("Edit conflict — reload and retry");
  if (!res.ok) throw new Error(`applyPreset failed: ${res.status}`);
  return res.json();
}
