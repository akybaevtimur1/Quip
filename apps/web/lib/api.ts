import type { CaptionPreset, CaptionTrack, ClipEdit, Job, Word } from "./types";

// База воркера: реальный worker через env, иначе встроенный мок (/api/mock).
const BASE = process.env.NEXT_PUBLIC_WORKER_URL ?? "/api/mock";

export type CreateJobInput = {
  source_type: "youtube";
  source_ref: string;
  max_clips?: number;
};

export async function createJob(input: CreateJobInput): Promise<{ id: string }> {
  const res = await fetch(`${BASE}/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(`createJob failed: ${res.status}`);
  return res.json();
}

export async function getJob(id: string): Promise<Job> {
  const res = await fetch(`${BASE}/jobs/${id}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`getJob failed: ${res.status}`);
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
