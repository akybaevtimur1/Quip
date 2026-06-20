"use client";

import { useEffect, useState } from "react";
import { CoWatch, type Moment } from "@/components/CoWatch";

// Dev-only harness (route /dev is OUTSIDE the auth gate) to eyeball the CoWatch visual without a
// full authed pipeline run. Uses a mock clip + mock markers that reveal progressively to demo the
// "lighting up" as the AI finds moments. NOT shipped UX — for screenshots/iteration only.

const MOCK: Moment[] = [
  { t: 1.5, kind: "question", intensity: 0.8, text: "why don't you remember your life?" },
  { t: 3.2, kind: "beat", intensity: 0.6, text: "here's the part nobody tells you" },
  { t: 5.0, kind: "emphasis", intensity: 0.95, text: "this changes everything" },
  { t: 7.4, kind: "stat", intensity: 0.7, text: "90% of the time we're on autopilot" },
  { t: 9.1, kind: "emphasis", intensity: 0.55, text: "and that's the real trap" },
  { t: 11.0, kind: "question", intensity: 0.75, text: "so what do you actually do?" },
  { t: 13.3, kind: "beat", intensity: 1.0, text: "wait for it…" },
  { t: 15.2, kind: "stat", intensity: 0.65, text: "it took 21 days to shift" },
  { t: 17.0, kind: "emphasis", intensity: 0.9, text: "you have to change the rules" },
  { t: 18.6, kind: "question", intensity: 0.7, text: "ready to try it?" },
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
        stageLabel={stageLabel}
        elapsed={elapsed}
      />
    </div>
  );
}
