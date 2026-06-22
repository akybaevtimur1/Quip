import type { CaptionReply, Word } from "@/lib/types";

// Утилиты позиционного соответствия реплик и слов клипа (зеркало бэкенда
// compile_ass: reply[i] покрывает words[offset .. offset+word_refs.length)).

/** Клип-временной диапазон активной реплики (в секундах, 0-based от outerStart). */
export interface ReplyRange {
  replyIndex: number;
  startSec: number;
  endSec: number;
}

/**
 * Клип-времена реплик из edit-state. Скрытые/пустые НЕ кликабельны, но всё
 * равно сдвигают offset (иначе позиционное соответствие слов поедет).
 */
export function buildReplyRanges(
  replies: CaptionReply[],
  words: Word[],
  outerStart: number,
): ReplyRange[] {
  const ranges: ReplyRange[] = [];
  let offset = 0;
  for (let i = 0; i < replies.length; i++) {
    const reply = replies[i];
    const count = reply.word_refs.length;
    const group = words.slice(offset, offset + count);
    offset += count;
    if (reply.hidden || count === 0 || group.length === 0) continue;
    ranges.push({
      replyIndex: i,
      startSec: Math.max(0, group[0].start - outerStart),
      endSec: Math.max(0, group[group.length - 1].end - outerStart),
    });
  }
  return ranges;
}

/**
 * Текст слов реплики (оригинал) — для начального значения textarea и сравнения
 * «правка == оригинал → снять override».
 */
export function originalReplyText(
  replies: CaptionReply[],
  words: Word[],
  replyIndex: number,
): string {
  let offset = 0;
  for (let i = 0; i < replies.length; i++) {
    const count = replies[i].word_refs.length;
    if (i === replyIndex) {
      return words
        .slice(offset, offset + count)
        .map((w) => w.text)
        .join(" ");
    }
    offset += count;
  }
  return "";
}

/** margin_v кламп в safe-диапазон (ASS-единицы, PlayResY=1920). */
export function clampMargin(m: number): number {
  return Math.max(40, Math.min(1200, Math.round(m)));
}

/**
 * Текст КАЖДОЙ видимой страницы субтитров (как она реально рисуется): override, иначе
 * слова реплики, в UPPERCASE если стиль так требует. Зеркалит позиционное соответствие
 * reply[i] ↔ words[offset..) (как buildReplyRanges / бэкенд compile_ass). Используется
 * авто-фитом (captionFit), чтобы подобрать ОДИН кегль, при котором ВСЕ страницы влезают
 * в рамку — скрытые/пустые реплики не дают страницы, но сдвигают offset.
 */
export function captionPageTexts(
  replies: CaptionReply[],
  words: Word[],
  uppercase: boolean,
): string[] {
  const pages: string[] = [];
  let offset = 0;
  for (const reply of replies) {
    const count = reply.word_refs.length;
    const group = words.slice(offset, offset + count);
    offset += count;
    if (reply.hidden || count === 0 || group.length === 0) continue;
    const text = reply.text_override ?? group.map((w) => w.text).join(" ");
    pages.push(uppercase ? text.toUpperCase() : text);
  }
  return pages;
}
