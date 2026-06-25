/*
  Quip landing - content layer (single source of truth for copy + data).
  Voice: measured, precise, a little dry. Honest. No fabricated proof.
  Numbers are exact per the brief. ZERO em-dashes anywhere (brand + taste rule).
*/

export type MomentType = "hook" | "peak" | "thought" | "quote";

export const TYPE_LABEL: Record<MomentType, string> = {
  hook: "Hook",
  peak: "Emotional peak",
  thought: "Complete thought",
  quote: "Strong quote",
};

export type Clip = {
  id: string;
  src?: string; // compressed mp4 in /public/clips
  poster?: string;
  hook: string;
  type: MomentType;
  confidence: number; // 0-100
  reason: string;
  timecode: string; // source range
  caption?: string; // the burned-in line visible in the still, for alt text
};

export const ROUTES = {
  signup: "/signup",
  app: "/dashboard",
  login: "/login",
  terms: "/terms",
  privacy: "/privacy",
};

export const NAV = [
  { label: "How it works", href: "#how-it-works" },
  { label: "Why Quip", href: "#why" },
  { label: "Pricing", href: "#pricing" },
  { label: "FAQ", href: "#faq" },
];

export const HERO = {
  eyebrow: "// CLIP STUDIO",
  // headline is split so one word can carry the lone coral chip
  headlinePre: "Don't just get clips.",
  headlineMid: "Know ",
  headlineAccent: "why",
  headlinePost: " they're worth posting.",
  // <= 20 words, fits the viewport. Fuller version lives in the demo section.
  sub: "Drop a podcast, interview, or stream. Quip cuts the few clips worth posting, and reports why each one lands.",
  primary: "Paste a video link",
  secondary: "See how it works",
  trust: "No card. 2 free videos / month.",
};

// The featured clip in the hero readout (a real captioned output).
// Hook + reason match this clip's real burned-in hook plate.
export const HERO_CLIP: Clip = {
  id: "03 / 23",
  src: "/clips/clip-1.mp4",
  poster: "/clips/poster-1.jpg",
  hook: "McConaughey's dad's surprising reaction to quitting law school",
  type: "thought",
  confidence: 94,
  reason: "Opens a loop in the title, then pays it off with a real turn. A complete story that stands on its own.",
  timecode: "00:14:22 → 00:14:49",
  caption: "His dad's surprising reaction.",
};

// Secondary real clip + a few representative readouts for the streaming grid.
export const CLIPS: Clip[] = [
  HERO_CLIP,
  {
    id: "07 / 23",
    src: "/clips/clip-2.mp4",
    poster: "/clips/poster-2.jpg",
    hook: "How Matthew McConaughey earned his dad's support",
    type: "thought",
    confidence: 88,
    reason: "A complete story with a clean payoff: he earned it by going all in, never by asking permission. It lands on its own.",
    timecode: "00:31:08 → 00:31:36",
    caption: "He didn't half-ass it.",
  },
  {
    id: "11 / 23",
    poster: "/clips/frame-1.jpg",
    hook: "The two seconds that decide everything",
    type: "hook",
    confidence: 91,
    reason: "A scroll-stopping cold open. States the stakes before the viewer can look away.",
    timecode: "00:42:55 → 00:43:19",
    caption: "Hook",
  },
  {
    id: "16 / 23",
    poster: "/clips/frame-5.jpg",
    hook: "Where it almost fell apart",
    type: "peak",
    confidence: 76,
    reason: "Genuine tension in the voice. Strong on emotion, lighter on a standalone payoff.",
    timecode: "00:51:30 → 00:52:02",
    caption: "Emotional peak",
  },
];

// Demo section
export const DEMO = {
  eyebrow: "A real run, end to end",
  heading: "Here's how it cuts, and why exactly like that.",
  sub: "One long video in. Quip finds the moments, cuts clean vertical clips, and reports the reason each one will land: a hook, a confidence score, and the cut explained.",
  stages: ["Upload", "Find the moments", "Cut vertical clips"],
};

// Cost anchor ledger. The single coral mark in this strip is the $0.
export const COST_ANCHOR = {
  eyebrow: "// THE MATH",
  cells: [
    { label: "Editor retainer", value: "$500 - 3,000", unit: "/ mo" },
    { label: "Per freelance clip", value: "$50 - 500", unit: "each" },
    { label: "To start on Quip", value: "$0", unit: "no card", accent: true },
  ],
};

export const HOW_IT_WORKS = {
  eyebrow: "// HOW IT WORKS",
  heading: "Long video in. Clips you can trust out.",
  sub: "Three steps, a couple of minutes.",
  steps: [
    {
      n: "01",
      title: "Paste a link or upload",
      body: "Drop a YouTube link or a file: podcast, interview, stream, or lecture. Up to 90 minutes.",
    },
    {
      n: "02",
      title: "Quip finds and explains",
      body: "It transcribes, picks the strongest moments, writes a hook, scores confidence, and reports why each one works.",
    },
    {
      n: "03",
      title: "Polish and post",
      body: "Smooth 9:16 reframe that follows the speaker, captions with punch, your style. Export and post with intent.",
    },
  ],
};

// The explainability payload: the four things every clip carries.
export const WHY = {
  eyebrow: "Why Quip",
  heading: "Every clip comes with its reasons.",
  sub: "Most AI clippers hand you thirty clips and a shrug. Quip hands you fewer, each with a hook, a confidence score, the moment type, and a plain reason it'll land. You post with intent, not hope.",
  payload: [
    { key: "Hook", body: "A scroll-stopping top line, written for that exact moment." },
    { key: "Why it works", body: "The real reason: open loop, payoff, tension, in one sentence." },
    { key: "Confidence", body: "An honest 0 to 100 score, so you know which clip to post first." },
    { key: "Moment type", body: "Hook, emotional peak, complete thought, or strong quote." },
  ],
};

export const CRAFT = {
  eyebrow: "// THE CRAFT",
  heading: "The cut is the easy part. We sweat the rest.",
  features: [
    {
      title: "Follows the speaker",
      body: "Active-speaker detection centers the right face, even in a multi-cam interview.",
    },
    {
      title: "No flash frames",
      body: "Frame-accurate scene detection. The crop only moves on a real cut, never mid-shot.",
    },
    {
      title: "Captions that pop",
      body: "The active word flares as it's spoken, burned in pixel for pixel. The preview is the export.",
    },
    {
      title: "Your hook, four ratios",
      body: "A branded hook plate on top, and 9:16, 1:1, 4:5, or 16:9 for every platform.",
    },
  ],
};

export const COMPARISON = {
  eyebrow: "// THE WEDGE",
  heading: "More clips was never the problem.",
  sub: "Knowing which moment is worth your audience's attention is.",
  cols: { quip: "Quip", them: "Volume clippers" },
  rows: [
    { k: "Clips per video", quip: "A few, ranked by confidence", them: "30+ to scroll through" },
    { k: "Why post each one", quip: "Hook, score, reason and type", them: "No idea, you guess" },
    { k: "Vertical reframe", quip: "Follows the speaker, zero flash frames", them: "Jumpy, often off-center" },
    { k: "Captions", quip: "Active word pops, your style", them: "Generic, one look" },
    { k: "Pricing", quip: "One credit = one video, shown up front", them: "Credit casino, surprise paywalls" },
    { k: "The result", quip: "Post with intent", them: "Post and hope" },
  ],
};

// The "rejected clips" proof for the comparison (the ones that did NOT make the cut).
export const CUT_PROOF = {
  kept: { label: "Made the cut", score: 94 },
  rejected: [
    { label: "Throat-clear intro", score: 38 },
    { label: "Tangent, no payoff", score: 44 },
    { label: "Talked over", score: 29 },
    { label: "Mid-sentence cut", score: 51 },
    { label: "Repeats the last point", score: 47 },
  ],
};

export type Plan = {
  id: string;
  name: string;
  price: string;
  cadence: string;
  blurb: string;
  allowance: string;
  features: string[];
  cta: string;
  href: string;
  recommended?: boolean;
};

export const PRICING = {
  eyebrow: "Pricing",
  heading: "Simple plans. No credit casino.",
  sub: "One credit is one video, up to 60 minutes. No tokens to ration, no surprise paywalls. Your limit is shown up front, and pay-as-you-go credits never expire.",
  plans: [
    {
      id: "free",
      name: "Free",
      price: "$0",
      cadence: "forever",
      blurb: "See it work, no card required.",
      allowance: "2 videos / mo · 120 min",
      features: [
        "Explainable clips with hook, score and reason",
        "Smooth 9:16 reframe that tracks the speaker",
        "Full editor and every caption style",
        "1080p export with a Quip watermark",
      ],
      cta: "Start free",
      href: ROUTES.signup,
    },
    {
      id: "starter",
      name: "Starter",
      price: "$15",
      cadence: "/ mo",
      blurb: "For creators shipping weekly.",
      allowance: "10 videos / mo · 600 min",
      features: [
        "Everything in Free",
        "No watermark, full 1080p",
        "All aspect ratios: 9:16, 1:1, 4:5, 16:9",
        "Top up anytime with pay-as-you-go",
      ],
      cta: "Choose Starter",
      href: ROUTES.signup,
    },
    {
      id: "pro",
      name: "Pro",
      price: "$35",
      cadence: "/ mo",
      blurb: "For heavy repurposing.",
      allowance: "30 videos / mo · 1,800 min",
      features: [
        "Everything in Starter",
        "Priority processing",
        "Early access to new features",
        "Pay-as-you-go when you need more",
      ],
      cta: "Choose Pro",
      href: ROUTES.signup,
      recommended: true,
    },
  ] as Plan[],
  payg: {
    name: "Pay-as-you-go",
    price: "$3",
    unit: "/ video",
    note: "No subscription. One video, never expires. Top up anytime.",
  },
  footnote: "Prices in USD. Cancel anytime. Monthly credits reset. Pay-as-you-go never expires.",
};

export const FAQ = {
  eyebrow: "// FAQ",
  heading: "Questions, answered straight.",
  items: [
    {
      q: "How is Quip different from OpusClip or Vizard?",
      a: "Most clippers optimize for volume: thirty clips you have to sift through. Quip optimizes for confidence: fewer clips, each with a hook, a confidence score, the moment type, and a plain reason it works. Add reframe with no flash frames and pricing without credit games, and you post with intent instead of hope.",
    },
    {
      q: "What kind of videos work best?",
      a: "Talking-heavy long-form: podcasts, interviews, streams, lectures, and webinars, up to 90 minutes. The more speech, the better the moments.",
    },
    {
      q: "Which languages does it support?",
      a: "Language is auto-detected. English and Russian work today, with more on the way.",
    },
    {
      q: "Do I keep my clips?",
      a: "Yes. Download them and they're yours. Paid plans export without a watermark.",
    },
    {
      q: "What is a credit?",
      a: "One credit is one video, up to 60 minutes of source. Longer videos use minutes proportionally (a 90-minute upload counts as 1.5). Your plan includes a set number of video-credits per month, so you always know your limit. Pay-as-you-go credits cost $3 each and never expire.",
    },
    {
      q: "Is the free plan actually free?",
      a: "Yes. 2 videos a month, that's 120 minutes of source to use however you like, no card required. Free exports carry a small watermark; paid plans drop it and export at full 1080p.",
    },
  ],
};

export const FINAL_CTA = {
  eyebrow: "// START",
  heading: "Stop guessing which clip to post.",
  sub: "Drop in a video and get a handful of clips you can stand behind, each with the reason it works and a score you can trust.",
  primary: "Try Quip free",
  secondary: "See pricing",
  trust: "No card. 2 free videos / month. Cancel anytime.",
};

export const FOOTER = {
  tagline: "Fewer clips, but you know why to post them. Explainable AI clips from your long videos.",
  cols: [
    {
      title: "Product",
      links: [
        { label: "How it works", href: "#how-it-works" },
        { label: "Why Quip", href: "#why" },
        { label: "Pricing", href: "#pricing" },
        { label: "FAQ", href: "#faq" },
      ],
    },
    {
      title: "Get started",
      links: [
        { label: "Create account", href: ROUTES.signup },
        { label: "Sign in", href: ROUTES.login },
        { label: "Open the app", href: ROUTES.app },
      ],
    },
    {
      title: "Legal",
      links: [
        { label: "Terms", href: ROUTES.terms },
        { label: "Privacy", href: ROUTES.privacy },
      ],
    },
  ],
  support: "Support and refunds: ceo@quip.ink",
  stripe: "© Quip. All rights reserved.",
  honesty: "Honest pricing. No credit casino. No surprise paywalls.",
};
