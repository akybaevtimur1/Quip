import type { ClipOut, Job, JobStatus } from "@/lib/types";

// Прогресс по времени с момента создания (id кодирует старт в base36).
const STAGES: { until: number; status: JobStatus; progress: number }[] = [
  { until: 2, status: "queued", progress: 5 },
  { until: 6, status: "downloading", progress: 20 },
  { until: 11, status: "transcribing", progress: 45 },
  { until: 16, status: "selecting", progress: 70 },
  { until: 22, status: "rendering", progress: 90 },
];

const MOCK_CLIPS: ClipOut[] = [
  {
    id: "clip_01",
    start: 170.8,
    end: 191.6,
    duration: 20.8,
    reason:
      "Сатира на вторую поправку и владение оружием — острый, самодостаточный обмен репликами, понятный без контекста.",
    type: "strong_quote",
    score: 0.85,
    video_url: "/mock/clip_01.mp4",
    thumbnail_url: null,
    transcript: "Mafia, townsperson, angel. Mike, this seems kinda discriminatory against second amendment…",
    words: [],
  },
  {
    id: "clip_05",
    start: 1895.1,
    end: 1937.7,
    duration: 42.5,
    reason:
      "Кульминация игры: игроки осознают, что убили Ангела — и мафия побеждает. Пиковая эмоция и развязка.",
    type: "emotional_peak",
    score: 0.96,
    video_url: "/mock/clip_05.mp4",
    thumbnail_url: null,
    transcript: "Moxie was kicked into a vat of piranhas, and the mafia win. Yeah. Let's go…",
    words: [],
  },
];

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<Response> {
  const { id } = await params;
  const ts = parseInt(id.replace("mock_", ""), 36);
  const elapsed = Number.isFinite(ts) ? (Date.now() - ts) / 1000 : 999;

  const stage = STAGES.find((s) => elapsed < s.until);
  if (stage) {
    const job: Job = {
      id,
      status: stage.status,
      stage: stage.status,
      progress: stage.progress,
      source_kind: "youtube",
      error: null,
      clips: [],
      metrics: null,
    };
    return Response.json(job);
  }

  const job: Job = {
    id,
    status: "done",
    stage: "done",
    progress: 100,
    source_kind: "youtube",
    error: null,
    clips: MOCK_CLIPS,
    metrics: { cost_usd: 0.16, duration_sec: 1987, elapsed_sec: Math.round(elapsed) },
  };
  return Response.json(job);
}
