"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { CaptionReply, CaptionStyle, HighlightStyle, Word } from "@/lib/types";

// ────────────────────────────────────────────────────────────────────────────
// Caption Engine v2 — живой рендер субтитров из модели стиля (CaptionStyle +
// HighlightStyle). НЕТ тёмной плашки по умолчанию (читаемость = контур + тень).
// Плашка всего блока — только если style.box_color задан. Караоке-подсветка
// активного слова по highlight (box / перекраска / scale). highlight=null →
// фраза целиком без караоке. См. docs .../2026-06-11-editor-v2-design.md §A.
// ────────────────────────────────────────────────────────────────────────────

const WORDS_PER_PAGE = 5;
const SENT_END = /[.!?…,]/;

// ASS-холст: PlayResY=1920. Размеры стиля заданы в этих единицах — переводим в
// пиксели относительно ВЫСОТЫ видео-контейнера (а не хардкод-px).
const ASS_PLAY_RES_Y = 1920;

// Дефолты модели (зеркало app/models.py CaptionStyle/HighlightStyle) — на случай
// частичного объекта из API.
const DEFAULT_STYLE: Required<CaptionStyle> = {
  font: "Montserrat",
  size: 90,
  color: "#FFFFFF",
  outline_color: "#000000",
  outline_w: 6,
  shadow: 2,
  box_color: null,
  box_opacity: 0.0,
  box_radius: 0,
  margin_v: 260,
  alignment: 2,
  uppercase: true,
  emphasis_color: null,
  emphasis_auto: true,
  // свободная позиция/ширина блока — None = центр + дефолтная ширина (CSS-фолбэк их не рендерит,
  // libass-превью/экспорт делают это через \pos + MarginL/R; тут только для полноты типа).
  pos_x: null,
  pos_y: null,
  wrap_width: null,
};

function resolveStyle(style?: CaptionStyle | null): Required<CaptionStyle> {
  return { ...DEFAULT_STYLE, ...(style ?? {}) };
}

// ── safe-area ──────────────────────────────────────────────────────────────
// Текст живёт в нижних ~78% высоты: bottom от margin_v, но не выше этого порога.
const SAFE_TOP_FRAC = 0.22; // верхние 22% — запретная зона
const MAX_WIDTH_FRAC = 0.92; // ширина ≤ 92%

interface Token {
  text: string;
  fromMs: number;
  toMs: number;
}

interface Page {
  startMs: number;
  endMs: number;
  tokens: Token[];
  // index into replies[] (positional) — для text_override и inline-правки
  replyIndex: number;
}

/**
 * Группировка слов в реплики (≤5 слов, разрыв на конце предложения при ≥2 словах).
 * Зеркалит логику бэка group_words достаточно для превью караоке.
 */
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

/**
 * Каноническая группировка из edit-state: reply[i] позиционно покрывает
 * words[offset .. offset+word_refs.length] (зеркало ClipEditor.captionGroups +
 * backend compile_ass). page.replyIndex = i (индекс в массиве replies) → правка
 * из оверлея (onCaptionsChange(replyIndex, …)) попадает в показанную реплику.
 * Скрытые/пустые реплики НЕ дают страницы (как `continue` в бэке), но всё равно
 * сдвигают offset на свою длину — иначе позиционное соответствие слов поедет.
 */
function buildPagesFromReplies(
  replies: CaptionReply[],
  words: Word[],
  clipStart: number,
): Page[] {
  const pages: Page[] = [];
  let offset = 0;
  const toMs = (w: Word) => Math.max(0, (w.start - clipStart) * 1000);
  const teMs = (w: Word) => Math.max(0, (w.end - clipStart) * 1000);
  for (let i = 0; i < replies.length; i++) {
    const reply = replies[i];
    const count = reply.word_refs.length;
    const group = words.slice(offset, offset + count);
    offset += count;
    // скрытые/пустые реплики не рисуем (но offset уже сдвинут выше)
    if (reply.hidden || count === 0 || group.length === 0) continue;
    pages.push({
      startMs: toMs(group[0]),
      endMs: teMs(group[group.length - 1]),
      tokens: group.map((w) => ({ text: w.text, fromMs: toMs(w), toMs: teMs(w) })),
      replyIndex: i,
    });
  }
  return pages;
}

/**
 * Жирный контур через многослойный text-shadow (text-stroke в Safari режет тонко).
 * Радиус контура масштабируем от высоты контейнера (как и размер шрифта).
 */
function buildTextShadow(outlineColor: string, outlinePx: number, shadowPx: number): string {
  const r = Math.max(0.5, outlinePx);
  const layers: string[] = [];
  // 8 направлений × 2 кольца → плотный контур без дыр
  const steps = 12;
  for (let k = 0; k < steps; k++) {
    const ang = (k / steps) * Math.PI * 2;
    const dx = Math.cos(ang) * r;
    const dy = Math.sin(ang) * r;
    layers.push(`${dx.toFixed(2)}px ${dy.toFixed(2)}px 0 ${outlineColor}`);
  }
  // дроп-тень под всем словом
  if (shadowPx > 0) {
    layers.push(`0 ${shadowPx.toFixed(1)}px ${(shadowPx * 1.2).toFixed(1)}px rgba(0,0,0,0.55)`);
  }
  return layers.join(", ");
}

export interface CaptionOverlayProps {
  // ── базовые (обратная совместимость) ──
  words: Word[];
  clipStart: number;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  /** text_override из replies (позиционно по replyIndex). */
  replies?: CaptionReply[] | null;

  // ── новые (Caption Engine v2) ──
  /** Модель стиля. Если не задана — дефолт пресета A. */
  style?: CaptionStyle | null;
  /** Караоке. null → без караоке (стиль D, фраза целиком). undefined → дефолт-караоке. */
  highlight?: HighlightStyle | null;
  /** true → inline-правка текста + тулбар (редактор). false → только показ (грид). */
  editing?: boolean;
  /** Колбэк при изменении текста реплики (inline-правка). Родитель шлёт PATCH. */
  onCaptionsChange?: (replyIndex: number, text: string | null) => void;
  /** Колбэк при изменении позиции (↕): новый margin_v (ASS-единицы). */
  onMarginChange?: (marginV: number) => void;
  /** Открыть полоску пресетов (🎨). */
  onStyleClick?: () => void;
  // jobId/clipId/version прокидываются родителем в onCaptionsChange-обработчик —
  // сам оверлей сетевых вызовов не делает (родитель владеет PATCH).
  jobId?: string;
  clipId?: string;
  version?: number;
}

export function CaptionOverlay({
  words,
  clipStart,
  videoRef,
  replies,
  style: styleProp,
  highlight: highlightProp,
  editing = false,
  onCaptionsChange,
  onMarginChange,
  onStyleClick,
}: CaptionOverlayProps) {
  const style = useMemo(() => resolveStyle(styleProp), [styleProp]);
  // highlight: undefined → дефолтное караоке; null → выключено (стиль D)
  const karaokeOff = highlightProp === null;
  const highlight: Required<HighlightStyle> = useMemo(
    () => ({
      color: highlightProp?.color ?? "#FF5A3D", // дефолт = коралл пресета A
      scale: highlightProp?.scale ?? 1.0,
      box: highlightProp?.box ?? false,
      animation: highlightProp?.animation ?? "karaoke_fill",
    }),
    [highlightProp],
  );

  // replies задан и непуст → каноническая группировка из edit-state (page i ↔
  // replies[i]); иначе → локальная buildPages (грид без edit-state).
  const pages = useMemo(
    () =>
      replies && replies.length > 0
        ? buildPagesFromReplies(replies, words, clipStart)
        : buildPages(words, clipStart),
    [replies, words, clipStart],
  );

  const [pageIdx, setPageIdx] = useState(-1);
  const [tokenIdx, setTokenIdx] = useState(-1);
  const prevPage = useRef(-1);
  const prevToken = useRef(-1);
  const rafRef = useRef<number>(0);

  // ── измеряем высоту контейнера, чтобы перевести ASS-единицы в px ──
  const wrapRef = useRef<HTMLDivElement>(null);
  const [containerH, setContainerH] = useState(0);
  useLayoutEffect(() => {
    const el = wrapRef.current?.parentElement;
    if (!el) return;
    const update = () => setContainerH(el.clientHeight);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // ── inline-edit state ──
  const [editIdx, setEditIdx] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // ── караоке-трекер по времени видео ──
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
      // между страницами держим ближайшую прошедшую (стабильность кадра)
      if (pi === -1) {
        for (let i = pages.length - 1; i >= 0; i--) {
          if (ms >= pages[i].startMs && ms < pages[i].startMs + 1) {
            pi = i;
            break;
          }
        }
      }

      let ti = -1;
      if (pi >= 0 && !karaokeOff) {
        const toks = pages[pi].tokens;
        for (let j = 0; j < toks.length; j++) {
          if (ms >= toks[j].fromMs && ms <= toks[j].toMs) {
            ti = j;
            break;
          }
        }
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
  }, [videoRef, pages, karaokeOff]);

  // В режиме правки: если плеер на паузе и страницы нет — показываем первую,
  // чтобы было что редактировать.
  const activePageIdx = pageIdx >= 0 ? pageIdx : editing && pages.length > 0 ? 0 : -1;
  const page = activePageIdx >= 0 ? pages[activePageIdx] : null;

  // фокус на textarea при входе в правку
  useEffect(() => {
    if (editIdx !== null && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editIdx]);

  if (!page || containerH === 0) {
    // всё равно держим wrapRef в DOM для измерения родителя
    return <div ref={wrapRef} className="absolute inset-0 pointer-events-none" aria-hidden />;
  }

  // ── ASS-единицы → px ──
  const scale = containerH / ASS_PLAY_RES_Y;
  const fontPx = Math.round(style.size * scale);
  const outlinePx = style.outline_w * scale;
  const shadowPx = style.shadow * scale;
  // bottom от margin_v, но кламп: текст не выше нижних (1 - SAFE_TOP_FRAC)
  const marginBottomPx = style.margin_v * scale;
  const maxBottomPx = containerH * (1 - SAFE_TOP_FRAC) - fontPx;
  const bottomPx = Math.min(marginBottomPx, Math.max(0, maxBottomPx));

  const textShadow = buildTextShadow(style.outline_color, outlinePx, shadowPx);
  const fontFamily =
    style.font === "Montserrat"
      ? "var(--font-display), 'Montserrat', system-ui, sans-serif"
      : `${style.font}, var(--font-display), system-ui, sans-serif`;

  // плашка всего блока — только если задана
  const blockBg =
    style.box_color != null
      ? hexWithOpacity(style.box_color, style.box_opacity || 1)
      : "transparent";

  const replyIdx = page.replyIndex;
  const override =
    replies && replyIdx < replies.length ? (replies[replyIdx]?.text_override ?? null) : null;
  const isEditingThis = editing && editIdx === replyIdx;

  const transformText = (t: string) => (style.uppercase ? t.toUpperCase() : t);

  const startEdit = () => {
    if (!editing) return;
    setDraft(override ?? page.tokens.map((t) => t.text).join(" "));
    setEditIdx(replyIdx);
  };

  const commitEdit = () => {
    if (editIdx === null) return;
    const trimmed = draft.trim();
    // редактируется ВСЕГДА активная страница (textarea рендерится только для
    // isEditingThis = active page), поэтому оригинал = её слова. editIdx —
    // это replyIndex, НЕ позиция в pages[] → индексировать pages[editIdx] нельзя.
    const original = page.tokens.map((t) => t.text).join(" ");
    // пустой или равный оригиналу → снять override (null)
    onCaptionsChange?.(editIdx, trimmed && trimmed !== original ? trimmed : null);
    setEditIdx(null);
  };

  const cancelEdit = () => setEditIdx(null);

  return (
    <div
      ref={wrapRef}
      className="pointer-events-none absolute inset-0 overflow-hidden"
      aria-hidden={!editing}
    >
      <div
        className="absolute left-1/2 -translate-x-1/2 text-center"
        style={{
          bottom: `${bottomPx}px`,
          width: `${MAX_WIDTH_FRAC * 100}%`,
          // полоса НЕ перехватывает клики (иначе блокирует видео/контролы);
          // кликабельны только тулбар и сам блок субтитра ниже (в editing).
          pointerEvents: "none",
          userSelect: editing ? "auto" : "none",
        }}
      >
        {/* мини-тулбар (режим правки) */}
        {editing && !isEditingThis && (
          <div
            className="mb-2 flex items-center justify-center gap-1"
            style={{ pointerEvents: "auto" }}
          >
            <ToolbarBtn title="Text" onClick={startEdit}>
              ✎
            </ToolbarBtn>
            {onMarginChange && (
              <>
                <ToolbarBtn
                  title="Move caption up"
                  onClick={() => onMarginChange(clampMargin(style.margin_v + 60))}
                >
                  ↑
                </ToolbarBtn>
                <ToolbarBtn
                  title="Move caption down"
                  onClick={() => onMarginChange(clampMargin(style.margin_v - 60))}
                >
                  ↓
                </ToolbarBtn>
              </>
            )}
            {onStyleClick && (
              <ToolbarBtn title="Style" onClick={onStyleClick}>
                🎨
              </ToolbarBtn>
            )}
          </div>
        )}

        <div
          onClick={editing && !isEditingThis ? startEdit : undefined}
          style={{
            display: "inline-block",
            maxWidth: "100%",
            background: blockBg,
            borderRadius: style.box_radius ? `${style.box_radius * scale}px` : undefined,
            padding: style.box_color != null ? `${4 * scale}px ${12 * scale}px` : undefined,
            cursor: editing && !isEditingThis ? "text" : "default",
            // только сам блок текста кликабелен в editing (остальное видео — нет)
            pointerEvents: editing ? "auto" : "none",
          }}
        >
          {isEditingThis ? (
            <textarea
              ref={inputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={commitEdit}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  commitEdit();
                } else if (e.key === "Escape") {
                  e.preventDefault();
                  cancelEdit();
                }
              }}
              rows={2}
              className="w-full resize-none bg-black/70 text-center outline-none"
              style={{
                fontFamily,
                fontWeight: 900,
                fontSize: `${fontPx}px`,
                lineHeight: 1.25,
                color: "#fff",
                borderRadius: `${8 * scale}px`,
                padding: `${4 * scale}px ${8 * scale}px`,
              }}
            />
          ) : karaokeOff || override ? (
            // фраза целиком (стиль D или отредактированный текст без пословных таймингов)
            <span
              style={{
                fontFamily,
                fontWeight: 900,
                fontSize: `${fontPx}px`,
                lineHeight: 1.25,
                color: style.color,
                textShadow,
                wordBreak: "break-word",
              }}
            >
              {transformText(override ?? page.tokens.map((t) => t.text).join(" "))}
            </span>
          ) : (
            // караоке: пословная подсветка
            <span
              className="inline-flex flex-wrap justify-center"
              style={{
                fontFamily,
                fontWeight: 900,
                fontSize: `${fontPx}px`,
                lineHeight: 1.25,
                columnGap: "0.3em",
                rowGap: `${4 * scale}px`,
              }}
            >
              {page.tokens.map((tok, i) => {
                const active = i === tokenIdx;
                if (active && highlight.box) {
                  // залитая плашка: текст тёмный, фон = highlight.color
                  return (
                    <span
                      key={i}
                      style={{
                        display: "inline-block",
                        color: "#000",
                        background: highlight.color,
                        borderRadius: `${6 * scale}px`,
                        padding: `0 ${7 * scale}px`,
                        transform: highlight.scale !== 1 ? `scale(${highlight.scale})` : undefined,
                        transition: "background 80ms ease, color 80ms ease",
                      }}
                    >
                      {transformText(tok.text)}
                    </span>
                  );
                }
                return (
                  <span
                    key={i}
                    style={{
                      display: "inline-block",
                      // box=false → перекраска активного слова в highlight.color
                      color: active ? highlight.color : style.color,
                      textShadow,
                      transform:
                        active && highlight.scale !== 1 ? `scale(${highlight.scale})` : undefined,
                      transformOrigin: "center bottom",
                      transition: "color 80ms ease, transform 80ms ease",
                    }}
                  >
                    {transformText(tok.text)}
                  </span>
                );
              })}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function ToolbarBtn({
  children,
  title,
  onClick,
}: {
  children: React.ReactNode;
  title: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className="inline-flex size-9 sm:size-7 items-center justify-center rounded-md bg-black/70 text-sm text-white/90 backdrop-blur transition hover:bg-accent hover:text-white"
    >
      {children}
    </button>
  );
}

// margin_v кламп в разумный safe-диапазон (ASS-единицы, PlayResY=1920).
function clampMargin(m: number): number {
  return Math.max(40, Math.min(900, Math.round(m)));
}

// #RRGGBB + opacity → rgba()
function hexWithOpacity(hex: string, opacity: number): string {
  const h = hex.replace("#", "");
  if (h.length !== 6) return hex;
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${Math.max(0, Math.min(1, opacity))})`;
}
