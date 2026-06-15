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

/** XHR с upload-progress + abort. Резолвит {status, responseText}. (fetch не даёт upload-progress.) */
function xhrRequest(
  method: string,
  url: string,
  body: XMLHttpRequestBodyInit | null,
  opts: {
    headers?: Record<string, string>;
    onProgress?: (pct: number) => void;
    signal?: AbortSignal;
  } = {},
): Promise<{ status: number; responseText: string }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, url);
    for (const [k, v] of Object.entries(opts.headers ?? {})) xhr.setRequestHeader(k, v);
    const { signal } = opts;
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
      if (e.lengthComputable && opts.onProgress) {
        opts.onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };
    xhr.onload = () => resolve({ status: xhr.status, responseText: xhr.responseText });
    xhr.onerror = () => reject(new Error("Upload failed — check your connection and try again"));
    xhr.send(body);
  });
}

export async function createUploadJob(
  file: File,
  maxClips?: number,
  onProgress?: (pct: number) => void,
  signal?: AbortSignal,
): Promise<{ id: string }> {
  const headers = await authHeaders();
  // 1. Спросить у воркера URL для ПРЯМОЙ загрузки браузер→R2 (cloud) или сигнал local-fallback.
  // Большие видео через ОДИН долгий POST на Modal web рвались (truncated multipart → 400 + CORS).
  // В облаке браузер PUT'ит файл ПРЯМО в R2 (Cloudflare edge, надёжно), минуя Modal web-функцию.
  const initRes = await fetch(`${BASE}/jobs/upload-url`, {
    method: "POST",
    headers: { ...headers, "Content-Type": "application/json" },
    body: JSON.stringify({ filename: file.name, max_clips: maxClips ?? null }),
    signal,
  });
  if (initRes.status === 401) throw new Error("Sign in to create clips.");
  if (initRes.status === 402) {
    const b = (await initRes.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(b?.detail ?? "Monthly limit reached. Upgrade your plan on the pricing page.");
  }
  if (!initRes.ok) throw new Error(`upload init failed: ${initRes.status}`);
  const init = (await initRes.json()) as { id?: string; put_url?: string; local?: boolean };

  if (init.put_url && init.id) {
    // 2. PUT файла ПРЯМО в R2 (XHR ради progress+abort). Content-Type в presigned URL не подписан
    //    → можно слать любой; ставим тип файла (R2 хранит). Нужен CORS на бакете (фаундер в дашборде).
    const put = await xhrRequest("PUT", init.put_url, file, {
      headers: { "Content-Type": file.type || "video/mp4" },
      onProgress,
      signal,
    });
    if (put.status < 200 || put.status >= 300) {
      throw new Error(`Upload to storage failed: ${put.status}`);
    }
    // 3. Финализация → воркер создаёт джоб + спавнит обработку.
    const done = await fetch(`${BASE}/jobs/${init.id}/upload-complete`, {
      method: "POST",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify({ filename: file.name, max_clips: maxClips ?? null }),
      signal,
    });
    if (!done.ok) throw new Error(`Couldn’t start processing: ${done.status}`);
    return { id: init.id };
  }

  // Local dev (нет R2): стримим через воркер — на localhost ок (старый multipart-путь).
  const form = new FormData();
  form.append("file", file);
  if (maxClips != null) form.append("max_clips", String(maxClips));
  const res = await xhrRequest("POST", `${BASE}/jobs/upload`, form, { headers, onProgress, signal });
  if (res.status === 401) throw new Error("Sign in to create clips.");
  if (res.status === 402) {
    let detail: string | undefined;
    try {
      detail = (JSON.parse(res.responseText) as { detail?: string }).detail;
    } catch {
      detail = undefined;
    }
    throw new Error(detail ?? "Monthly limit reached. Upgrade your plan on the pricing page.");
  }
  if (res.status < 200 || res.status >= 300) {
    throw new Error(`createUploadJob failed: ${res.status}`);
  }
  try {
    return JSON.parse(res.responseText) as { id: string };
  } catch {
    throw new Error("createUploadJob: invalid server response");
  }
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
