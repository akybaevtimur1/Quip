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
  monthly_credits: number;
  used_credits: number;
  remaining_credits: number;
  payg_credits: number;
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
  if (res.status === 401) throw new Error("Войдите в аккаунт, чтобы создавать клипы.");
  if (res.status === 402) {
    const body = (await res.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? "Месячный лимит исчерпан. Обновите тариф на странице тарифов.");
  }
}

export async function createUploadJob(
  file: File,
  maxClips?: number,
): Promise<{ id: string }> {
  const form = new FormData();
  form.append("file", file);
  if (maxClips != null) form.append("max_clips", String(maxClips));
  // НЕ задаём Content-Type вручную — браузер сам выставит multipart boundary.
  const res = await fetch(`${BASE}/jobs/upload`, {
    method: "POST",
    headers: await authHeaders(),
    body: form,
  });
  await throwOnAuthOrQuota(res);
  if (!res.ok) throw new Error(`createUploadJob failed: ${res.status}`);
  return res.json();
}

/** Живой расход (план + остаток кредитов) для UsageMeter. Бросает при недоступности —
 *  UsageMeter откатывается на дефолт free (dual-mode без воркера/auth). */
export async function getUsage(): Promise<UsageInfo> {
  const res = await fetch(`${BASE}/usage`, { cache: "no-store", headers: await authHeaders() });
  if (!res.ok) throw new Error(`getUsage failed: ${res.status}`);
  return res.json();
}

export async function getJob(id: string): Promise<Job> {
  const res = await fetch(`${BASE}/jobs/${id}`, { cache: "no-store" });
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
