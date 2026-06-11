"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Word } from "@/lib/types";

const WORDS_PER_PAGE = 5;
const SENT_END = /[.!?…,]/;

interface Page {
  startMs: number;
  endMs: number;
  tokens: { text: string; fromMs: number; toMs: number }[];
}

function buildPages(words: Word[], clipStart: number): Page[] {
  if (words.length === 0) return [];
  const pages: Page[] = [];
  let i = 0;
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
    });
  }
  return pages;
}

interface Props {
  words: Word[];
  clipStart: number;
  videoRef: React.RefObject<HTMLVideoElement | null>;
}

export function CaptionOverlay({ words, clipStart, videoRef }: Props) {
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
        if (ms >= pages[i].startMs && ms <= pages[i].endMs) { pi = i; break; }
      }

      let ti = -1;
      if (pi >= 0) {
        const toks = pages[pi].tokens;
        for (let j = 0; j < toks.length; j++) {
          if (ms >= toks[j].fromMs && ms <= toks[j].toMs) { ti = j; break; }
        }
        // if between words, keep previous token highlighted
        if (ti === -1 && ms > pages[pi].startMs) {
          for (let j = toks.length - 1; j >= 0; j--) {
            if (ms > toks[j].fromMs) { ti = j; break; }
          }
        }
      }

      if (pi !== prevPage.current) { setPageIdx(pi); prevPage.current = pi; }
      if (ti !== prevToken.current) { setTokenIdx(ti); prevToken.current = ti; }

      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [videoRef, pages]);

  const page = pageIdx >= 0 ? pages[pageIdx] : null;
  if (!page) return null;

  return (
    <div
      className="absolute bottom-14 left-0 right-0 px-4 text-center pointer-events-none select-none"
      aria-hidden
    >
      <span
        className="font-display text-[22px] font-black uppercase leading-snug"
        style={{
          textShadow:
            "1px 1px 0 #000,-1px -1px 0 #000,1px -1px 0 #000,-1px 1px 0 #000,0 3px 10px rgba(0,0,0,0.9)",
        }}
      >
        {page.tokens.map((tok, i) => {
          const active = i === tokenIdx;
          return (
            <span key={i} style={{ display: "inline-block", paddingInline: "0.18em" }}>
              <span
                style={{
                  display: "inline-block",
                  transition: "color 60ms ease, transform 60ms ease",
                  color: active ? "#ff5a3d" : "#ffffff",
                  transform: active ? "scale(1.12)" : "scale(1)",
                  transformOrigin: "bottom center",
                }}
              >
                {tok.text}
              </span>
            </span>
          );
        })}
      </span>
    </div>
  );
}
