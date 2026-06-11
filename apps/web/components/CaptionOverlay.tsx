"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { CaptionReply, Word } from "@/lib/types";

const WORDS_PER_PAGE = 5;
const SENT_END = /[.!?…,]/;

// Accent color for the active-word highlight box.
const HIGHLIGHT_COLOR = "#ff5a3d"; // coral (matches brand --color-accent)

interface Page {
  startMs: number;
  endMs: number;
  tokens: { text: string; fromMs: number; toMs: number }[];
  // index into replies[] if we have override text
  replyIndex: number;
}

function buildPages(words: Word[], clipStart: number): Page[] {
  if (words.length === 0) return [];
  const pages: Page[] = [];
  let i = 0;
  let replyIndex = 0;
  while (i < words.length) {
    const chunk: Word[] = [];
    while (chunk.length < WORDS_PER_PAGE && i < words.length) {
      chunk.push(words[i]);
      const endsChunk = SENT_END.test(words[i].text) && chunk.length >= 2;
      i++;
      if (endsChunk) break;
    }
    const toMs = (w: Word) => Math.max(0, (w.start - clipStart) * 1000);
    const teMs = (w: Word) => Math.max(0, (w.end - clipStart) * 1000);
    pages.push({
      startMs: toMs(chunk[0]),
      endMs: teMs(chunk[chunk.length - 1]),
      tokens: chunk.map((w) => ({ text: w.text, fromMs: toMs(w), toMs: teMs(w) })),
      replyIndex,
    });
    replyIndex++;
  }
  return pages;
}

interface Props {
  words: Word[];
  clipStart: number;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  // optional: when editor is open, use edited text_override from replies
  replies?: CaptionReply[] | null;
}

export function CaptionOverlay({ words, clipStart, videoRef, replies }: Props) {
  const pages = useMemo(() => buildPages(words, clipStart), [words, clipStart]);

  const [pageIdx, setPageIdx] = useState(-1);
  const [tokenIdx, setTokenIdx] = useState(-1);
  const prevPage = useRef(-1);
  const prevToken = useRef(-1);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || pages.length === 0) return;

    const tick = () => {
      const ms = video.currentTime * 1000;

      let pi = -1;
      for (let i = 0; i < pages.length; i++) {
        if (ms >= pages[i].startMs && ms <= pages[i].endMs) {
          pi = i;
          break;
        }
      }

      let ti = -1;
      if (pi >= 0) {
        const toks = pages[pi].tokens;
        for (let j = 0; j < toks.length; j++) {
          if (ms >= toks[j].fromMs && ms <= toks[j].toMs) {
            ti = j;
            break;
          }
        }
        // if between words keep the last highlighted token visible
        if (ti === -1 && ms > pages[pi].startMs) {
          for (let j = toks.length - 1; j >= 0; j--) {
            if (ms > toks[j].fromMs) {
              ti = j;
              break;
            }
          }
        }
      }

      if (pi !== prevPage.current) {
        setPageIdx(pi);
        prevPage.current = pi;
      }
      if (ti !== prevToken.current) {
        setTokenIdx(ti);
        prevToken.current = ti;
      }

      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [videoRef, pages]);

  const page = pageIdx >= 0 ? pages[pageIdx] : null;
  if (!page) return null;

  // Check for edited text override for this page
  const override =
    replies && page.replyIndex < replies.length
      ? replies[page.replyIndex]?.text_override ?? null
      : null;

  return (
    <div
      className="absolute left-0 right-0 px-3 text-center pointer-events-none select-none"
      // 260/1920 ≈ 13.5% from bottom — matches ASS MarginV=260 so overlay covers burned-in subs
      style={{ bottom: "13.5%" }}
      aria-hidden
    >
      {/* Dark strip behind all words covers burned-in ASS on any background */}
      <div
        style={{
          display: "inline-block",
          background: "rgba(0,0,0,0.72)",
          borderRadius: "8px",
          padding: "4px 10px 6px",
          maxWidth: "92%",
        }}
      >
        {override ? (
          // Edited text: show as one block, no per-word animation (no word timings available)
          <span
            className="font-display font-black uppercase"
            style={{ fontSize: "clamp(18px, 4.5vw, 26px)", lineHeight: 1.3, color: "#fff" }}
          >
            {override}
          </span>
        ) : (
          // Normal mode: per-word karaoke highlight
          <span
            className="inline-flex flex-wrap justify-center gap-x-[0.3em] gap-y-1 font-display font-black uppercase"
            style={{ fontSize: "clamp(18px, 4.5vw, 26px)", lineHeight: 1.3 }}
          >
            {page.tokens.map((tok, i) => {
              const active = i === tokenIdx;
              return (
                <span
                  key={i}
                  style={{
                    display: "inline-block",
                    color: active ? "#000" : "#fff",
                    background: active ? HIGHLIGHT_COLOR : "transparent",
                    borderRadius: "5px",
                    padding: active ? "0 7px 1px" : "0 1px",
                    transition: "background 80ms ease, color 80ms ease",
                    textShadow: active
                      ? "none"
                      : undefined,
                  }}
                >
                  {tok.text}
                </span>
              );
            })}
          </span>
        )}
      </div>
    </div>
  );
}
