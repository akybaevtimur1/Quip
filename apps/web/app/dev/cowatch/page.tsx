"use client";

import { useEffect, useState } from "react";
import { CoWatch, type Moment } from "@/components/CoWatch";

// Dev-only harness (route /dev is OUTSIDE the auth gate) to eyeball the CoWatch visual without a
// full authed pipeline run. Uses a mock clip + mock markers that reveal progressively to demo the
// "lighting up" as the AI finds moments. NOT shipped UX — for screenshots/iteration only.

const MOCK: Moment[] = [
  { t: 1.5, kind: "question", intensity: 0.8 },
  { t: 3.2, kind: "beat", intensity: 0.6 },
  { t: 5.0, kind: "emphasis", intensity: 0.95 },
  { t: 7.4, kind: "stat", intensity: 0.7 },
  { t: 9.1, kind: "emphasis", intensity: 0.55 },
  { t: 11.0, kind: "question", intensity: 0.75 },
  { t: 13.3, kind: "beat", intensity: 1.0 },
  { t: 15.2, kind: "stat", intensity: 0.65 },
  { t: 17.0, kind: "emphasis", intensity: 0.9 },
  { t: 18.6, kind: "question", intensity: 0.7 },
];
const STAGES = ["Preparing your video", "Transcribing", "Finding the moments worth posting"];

export default function CoWatchDevPage() {
  const [n, setN] = useState(0); // how many markers revealed
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const reveal = setInterval(() => setN((x) => Math.min(MOCK.length, x + 1)), 800);
    const tick = setInterval(() => setElapsed((x) => x + 1), 1000);
    return () => {
      clearInterval(reveal);
      clearInterval(tick);
    };
  }, []);

  const stageLabel = STAGES[Math.min(STAGES.length - 1, Math.floor(n / 4))];

  return (
    <div className="flex min-h-dvh items-center justify-center bg-bg p-8">
      <CoWatch
        src="/mock/clip_01.mp4"
        moments={MOCK.slice(0, n)}
        durationSec={20}
        stageLabel={stageLabel}
        elapsed={elapsed}
      />
    </div>
  );
}
