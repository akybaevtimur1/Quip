import type { VideoMap } from "@/lib/types";

// Реалистичный мок VideoMap — status=done с нарративом, 2-мя главами и 6-ю моментами.
// Narrative содержит [mm:ss]-тайм-код (clip_01 покрывает 170.8–191.6 с) и [[clip:clip_02]]-ссылку.
const MOCK_VIDEO_MAP: VideoMap = {
  status: "done",
  narrative:
    "This video is a recording of a Mafia game full of unexpected twists. Early on [2:50] the players " +
    "slowly work out the rules, but by the middle the cozy mood breaks down: someone accuses " +
    "an innocent townsperson. The climax — [[clip:clip_02]] — is the moment the mafia flips the " +
    "outcome at the very last second. The video is a perfect source for clips: plenty of " +
    "sharp exchanges and rich emotional peaks.",
  chapters: [
    {
      title: "Opening: learning the rules",
      start: 0,
      end: 600,
      summary:
        "Players get their roles and figure out the mechanics. The humor is that nobody quite " +
        "knows who the mafia is.",
      clip_ids: ["clip_01"],
      moments: [
        {
          kind: "funny",
          label: "Mixed-up roles",
          why: "A mafia player forgets their role and accidentally gives themselves away",
          start: 45,
          end: 62,
        },
        {
          kind: "quote",
          label: "“Isn't that discrimination against the Second Amendment?”",
          why: "An absurd line about the Second Amendment that instantly became a meme",
          start: 172,
          end: 185,
        },
        {
          kind: "tension",
          label: "The first vote",
          why: "A tense vote: a single ballot decides an innocent player's fate",
          start: 520,
          end: 558,
        },
      ],
    },
    {
      title: "Finale: the mafia wins at the last moment",
      start: 600,
      end: 1987,
      summary:
        "The townsfolk think they've found the mafia, but they kill the Angel — and the mafia wins. " +
        "Peak emotion and a resolution worth watching to the end for.",
      clip_ids: ["clip_05"],
      moments: [
        {
          kind: "tension",
          label: "The Angel is accused",
          why: "An innocent player is on the chopping block — the room goes quiet",
          start: 1820,
          end: 1850,
        },
        {
          kind: "emotional",
          label: "The Angel is eliminated",
          why: "The players are stunned — they executed the wrong person",
          start: 1893,
          end: 1910,
        },
        {
          kind: "insight",
          label: "The moment of realization",
          why: "The host explains exactly what went wrong — a clear breakdown of the mistake",
          start: 1940,
          end: 1965,
        },
      ],
    },
  ],
};

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<Response> {
  // id param required by Next.js dynamic segment, not used for mock
  await params;
  return Response.json(MOCK_VIDEO_MAP);
}
