# Quip — Landing Demo: Real-Pipeline Recording + Montage Guide

The demo must show the **real product in action**: you drop one long video in, and Quip fans it
out into explained vertical clips. That live transformation IS the pitch. The challenge is that the
real pipeline takes minutes — so we record the full flow once, then **speed-ramp the waiting** in
editing so it looks fast. Because it's pre-recorded, it plays **instantly** on the landing (visitors
never wait for the real pipeline).

---

## 1. What to record (one continuous screen capture)

Record the whole flow in a single take — don't worry about the long waits, we cut them:

1. **Dashboard** with a video file ready → **drag it in → click "Make clips."**
2. **"Reading your video"** — the co-watch view: the source plays while **moment quotes** pop over it.
3. **"Cutting your video"** — the steps tick: Preparing → Transcribing → **Selecting moments** → Rendering.
4. **The grid fills** with clips — each with a **hook**, a **"Why it works"** line, and a **confidence
   score**. Linger here ~3–4s; this is the payoff and the differentiator (explainability).
5. **Click one clip → editor** → the **vertical clip plays with animated captions + the hook** on top.
6. End on the **finished vertical clip** (or hit Download to show the export).

> Tip: use a **SHORT source (~3–5 min, not 77)** so processing is quick and the take stays short. A
> 77-min source takes ~15+ min to fully render 30 clips — too long even sped up.

---

## 2. How to record

- **Tool:** OBS Studio (free, best quality) or Windows **Win+G** game bar / Mac Cmd+Shift+5.
- **Browser:** 1920×1080, zoom ~100–110% so text is legible, hide bookmarks bar + extensions, clean tab.
- **One take.** Re-do freely — we trim later. Mouse movements smooth, no frantic hunting.
- You must be **logged in** on `quip.ink` (your normal browser) — the editor + dashboard are gated.

---

## 3. How to montage (CapCut = easiest: free, speed-ramp + music + text)

The whole trick is compressing the minutes of processing into seconds.

- **Cut the dead time:** select the "Reading / Cutting your video" stretch → **speed it up 10–30×**
  (timelapse) so it flies by in ~3s. Hard-cut from "uploading" straight into "clips appearing."
- **Target ~20–25s, structure:**
  1. (2s) Drop the video + click **Make clips**.
  2. (3s) **Sped-up processing** — moment quotes flashing, the step list ticking.
  3. (5s) **Grid fills** with explained clips (hooks + scores) — slow it back to real-time here.
  4. (6s) Click a clip → **editor** → the **captioned vertical clip plays**.
  5. (3s) End card: the finished vertical clip + **"Make clips free."**
- **Polish:** upbeat music; 2–3 quick zoom-ins (on a hook, on a 0.9x score); on-screen labels —
  **"Upload" → "AI finds the moments" → "Get vertical clips, with the why."**
- **Export:** 1080p MP4 (H.264). For the landing, **mute + loop** it.

Alt editors: **DaVinci Resolve** (free, pro, best speed-ramp control), Premiere, Final Cut.

---

## 4. Mounting on the landing

Assets go in `apps/web/public/demo/`. Autoplay muted loop with a poster for instant paint:

```html
<video autoplay muted loop playsinline preload="metadata"
       poster="/demo/quip-demo-poster.jpg" class="rounded-2xl shadow-2xl">
  <source src="/demo/quip-demo.webm" type="video/webm" />
  <source src="/demo/quip-demo.mp4"  type="video/mp4" />
</video>
```

Add a `prefers-reduced-motion` fallback (show the poster, no autoplay).

> Send me the raw screen recording and I'll do the montage in ffmpeg (cut, speed-ramp the waiting,
> add labels, compress, loop, poster) and hand back the web-ready files + the snippet above.

---

## Appendix — the output-clip reel (already built)

A separate asset already exists in `apps/web/public/demo/` (`quip-demo.mp4/.webm` + poster): a 25s
vertical loop of 5 real clips Quip cut from the 77-min podcast, each with its hook burned on. Useful
as a "here's what you get" card even if the hero uses the real-pipeline recording above.
