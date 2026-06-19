"use client";

import { useEffect, useRef } from "react";
import type SubtitlesOctopus from "libass-wasm";
import type { OctopusRenderCanvasMessage } from "libass-wasm";
import { type SubRects, rectToFractions, splitHookCaptionAss } from "@/lib/overlayBox";

// ────────────────────────────────────────────────────────────────────────────
// LibassLayer — обёртка SubtitlesOctopus (libass.wasm, MIT) в CANVAS-режиме.
// Рисует ТОТ ЖЕ ASS, что жжёт ffmpeg на экспорте → превью = экспорт
// пиксель-в-пиксель.
//
// ПОЧЕМУ канвас-режим (а не video-режим): video-режим позиционирует канвас по
// letterbox-геометрии видео-элемента (object-contain). У нас превью = 9:16
// контейнер с object-COVER кропом источника, а ASS свёрстан под полный
// 1080×1920-кадр → канвас обязан заполнять ВЕСЬ контейнер. Поэтому держим свой
// <canvas> (absolute inset-0), задаём размер сами (ResizeObserver + resize())
// и гоним время вручную: setCurrentTime(video.currentTime − sourceStart) в rAF.
// Бонус: смена sourceStart больше НЕ пересоздаёт тяжёлый WASM-инстанс.
//
// ДВА ИНСТАНСА (hook / caption): хук (\an8, сверху) и субтитры (\an2, снизу) рисуем
// РАЗДЕЛЬНО — по одному ASS на инстанс (splitHookCaptionAss). Так fused-rect каждого
// инстанса (libass в wasm-blend постит ОДИН union-bbox на кадр) = ТОЧНЫЙ bbox именно
// своего элемента, без хрупкого дробления union'а. Пиксели идентичны единому ASS:
// хук и субтитры НЕ пересекаются пространственно, два канваса (absolute inset-0)
// компонуются поверх. Каждый worker-message `op:"renderCanvas"` несёт canvases[0]
// (device px) → конвертим в доли рендер-бокса → onSubRects (для CapCut-рамки).
//
// При ошибке НЕ кидает — зовёт props.onError, родитель показывает CSS-фолбэк.
// ────────────────────────────────────────────────────────────────────────────

interface LibassLayerProps {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  assText: string;
  sourceStart: number;
  onError?: () => void;
  /**
   * Per-frame rendered rects of hook / caption as render-box fractions (throttled to
   * animation frames). Drives the CapCut selection box off libass's REAL geometry.
   */
  onSubRects?: (rects: SubRects) => void;
}

// One rendered libass instance + the canvas it draws into + a tap on its worker that
// reads the per-frame fused rect. `kind` selects which slot of SubRects it fills.
interface Slot {
  kind: "hook" | "caption";
  canvas: HTMLCanvasElement;
  instance: SubtitlesOctopus | null;
  /** Latest fused blend rect (device px) from the worker, or null when nothing drawn. */
  rect: { x: number; y: number; w: number; h: number } | null;
  onMessage: ((e: MessageEvent) => void) | null;
}

export function LibassLayer({
  videoRef,
  assText,
  sourceStart,
  onError,
  onSubRects,
}: LibassLayerProps) {
  const hookCanvasRef = useRef<HTMLCanvasElement>(null);
  const captionCanvasRef = useRef<HTMLCanvasElement>(null);
  const slotsRef = useRef<Slot[]>([]);
  // ref'ы вместо deps: правки ASS/интервала/колбэка не должны пересоздавать WASM-инстансы
  const assRef = useRef(assText);
  const startRef = useRef(sourceStart);
  const onErrorRef = useRef(onError);
  const onSubRectsRef = useRef(onSubRects);
  // Базовая точка троттла рендера — ОБЩАЯ между rAF-циклом и эффектом setTrack.
  // Сброс в -1 форсит немедленный редроу при смене ASS (иначе на ПАУЗЕ время не
  // меняется → setCurrentTime не зовётся → libass держит СТАРЫЙ кадр трека).
  const lastTRef = useRef(-1);
  useEffect(() => {
    assRef.current = assText;
    startRef.current = sourceStart;
    onErrorRef.current = onError;
    onSubRectsRef.current = onSubRects;
  });

  // ── создание инстансов (один раз на mount) + размер + rAF-синк времени ──
  useEffect(() => {
    const hookCanvas = hookCanvasRef.current;
    const captionCanvas = captionCanvasRef.current;
    const video = videoRef.current;
    if (!hookCanvas || !captionCanvas || !video || !assRef.current) return;

    let disposed = false;
    let raf = 0;
    let ro: ResizeObserver | null = null;

    const slots: Slot[] = [
      { kind: "hook", canvas: hookCanvas, instance: null, rect: null, onMessage: null },
      { kind: "caption", canvas: captionCanvas, instance: null, rect: null, onMessage: null },
    ];
    slotsRef.current = slots;

    // Convert each slot's latest device-px rect to render-box fractions and surface them.
    // Canvas is 1:1 with the render box (absolute inset-0 size-full), so canvas pixel size
    // is the basis for the fraction. Emitted on every worker render frame (already throttled
    // by the worker's targetFps + our setCurrentTime throttle).
    const emitRects = () => {
      const cb = onSubRectsRef.current;
      if (!cb) return;
      const out: SubRects = { hook: null, caption: null };
      for (const slot of slots) {
        out[slot.kind] = slot.rect
          ? rectToFractions(slot.rect, slot.canvas.width, slot.canvas.height)
          : null;
      }
      cb(out);
    };

    // размер каждого канваса = размер контейнера (CSS-пиксели × DPR). Канвас обязан
    // попиксельно совпадать с РЕНДЕР-боксом в ОБОИХ режимах; на входе/выходе из fullscreen
    // бокс меняет CSS-размер и DPR может не измениться → одного ResizeObserver мало,
    // поэтому дополнительно пере-меряем на fullscreenchange и window resize.
    const applySize = () => {
      const box = hookCanvas.parentElement;
      if (!box) return;
      const r = box.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const w = Math.max(1, Math.round(r.width * dpr));
      const h = Math.max(1, Math.round(r.height * dpr));
      for (const slot of slots) {
        try {
          slot.instance?.resize(w, h);
        } catch {
          /* инстанс мог умереть — onError уже сработал */
        }
      }
      // канвас изменил размер → доли пересчитать (даже без нового кадра от воркера)
      emitRects();
    };
    const onRelayout = () => applySize();

    (async () => {
      try {
        const SubtitlesOctopusCtor = (await import("libass-wasm")).default;
        if (disposed) return;
        const parts = splitHookCaptionAss(assRef.current);

        for (const slot of slots) {
          const sub = parts[slot.kind];
          // Нет события данного типа (хук выключен / нет реплик) → не поднимаем тяжёлый
          // WASM-инстанс под пустой трек (libass #166 пустой трек всё равно не рисует).
          if (!sub) continue;
          const inst = new SubtitlesOctopusCtor({
            canvas: slot.canvas,
            subContent: sub,
            workerUrl: "/libass/subtitles-octopus-worker.js",
            legacyWorkerUrl: "/libass/subtitles-octopus-worker-legacy.js",
            // тот же набор, что у ffmpeg-экспорта (services/worker/fonts) — WYSIWYG
            fonts: [
              "/libass/fonts/Montserrat.ttf",
              "/libass/fonts/Unbounded.ttf",
              "/libass/fonts/Rubik.ttf",
            ],
            // дефолтный fallback = default.woff2 РЯДОМ С ВОРКЕРОМ — мы его не хостим,
            // воркер падал «Loading data file default.woff2 failed». Наш fallback —
            // Montserrat (есть кириллица), файл хостится.
            fallbackFont: "/libass/fonts/Montserrat.ttf",
            onError: (e?: unknown) => {
              const msg =
                e instanceof ErrorEvent ? e.message : e instanceof Error ? e.message : String(e);
              console.error("[libass] init/worker error:", msg || "(без деталей)");
              onErrorRef.current?.();
            },
          });
          slot.instance = inst;

          // ── tap the worker's per-frame fused rect (ADD-ONLY: rendering unchanged) ──
          // The bundled worker posts {target:"canvas", op:"renderCanvas", canvases:[{x,y,w,h,buffer}]}
          // every frame in wasm-blend mode: canvases[0] = union bbox of everything this instance
          // drew (this instance = exactly hook OR caption). Empty canvases ⇒ nothing on screen now.
          // (subtitles-octopus.js handles the SAME message to actually paint — we only listen.)
          const worker = inst.worker;
          if (worker) {
            const onMessage = (e: MessageEvent) => {
              const data = e.data as Partial<OctopusRenderCanvasMessage> | undefined;
              if (!data || data.target !== "canvas" || data.op !== "renderCanvas") return;
              const first = data.canvases?.[0];
              slot.rect =
                first && first.w > 0 && first.h > 0
                  ? { x: first.x, y: first.y, w: first.w, h: first.h }
                  : null;
              emitRects();
            };
            worker.addEventListener("message", onMessage);
            slot.onMessage = onMessage;
          }
        }

        applySize();
        ro = new ResizeObserver(applySize);
        if (hookCanvas.parentElement) ro.observe(hookCanvas.parentElement);
        document.addEventListener("fullscreenchange", onRelayout);
        window.addEventListener("resize", onRelayout);

        // время: ASS в клип-времени, видео в source-времени. Троттл ~30Гц.
        lastTRef.current = -1;
        const tick = () => {
          if (disposed) return;
          const t = Math.max(0, video.currentTime - startRef.current);
          if (Math.abs(t - lastTRef.current) >= 1 / 30) {
            lastTRef.current = t;
            for (const slot of slots) {
              try {
                slot.instance?.setCurrentTime(t);
              } catch {
                /* noop */
              }
            }
          }
          raf = requestAnimationFrame(tick);
        };
        raf = requestAnimationFrame(tick);
      } catch {
        if (!disposed) onErrorRef.current?.();
      }
    })();

    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      ro?.disconnect();
      document.removeEventListener("fullscreenchange", onRelayout);
      window.removeEventListener("resize", onRelayout);
      for (const slot of slots) {
        if (slot.instance?.worker && slot.onMessage) {
          slot.instance.worker.removeEventListener("message", slot.onMessage);
        }
        if (slot.instance) {
          try {
            slot.instance.dispose();
          } catch {
            /* dispose не должен ронять размонтирование */
          }
        }
      }
      slotsRef.current = [];
    };
  }, [videoRef]);

  // ── живое обновление треков при смене assText (БЕЗ пересоздания) ──
  // setTrack ЗАМЕНЯЕТ трек. После setTrack нужен принудительный редроу на ТЕКУЩЕМ
  // времени (особенно на паузе, где rAF-троттл время не двигает). Каждый инстанс
  // получает СВОЮ часть (hook/caption) из расщеплённого ASS. Если у инстанса теперь
  // нет своих событий — пустой трек НЕ сетим (libass #166 не рендерит пустой → мусор);
  // включение хука/субтитров «с нуля» (инстанса ещё нет) добирает remount-ключ родителя.
  useEffect(() => {
    const slots = slotsRef.current;
    if (slots.length === 0 || !assText.trim()) return;
    const parts = splitHookCaptionAss(assText);
    const video = videoRef.current;
    const t = video ? Math.max(0, video.currentTime - startRef.current) : 0;
    lastTRef.current = -1;
    for (const slot of slots) {
      const inst = slot.instance;
      const sub = parts[slot.kind];
      if (!inst || !sub) continue;
      try {
        inst.setTrack(sub);
        inst.setCurrentTime(t);
      } catch {
        onErrorRef.current?.();
      }
    }
  }, [assText, videoRef]);

  return (
    <>
      <canvas
        ref={hookCanvasRef}
        className="pointer-events-none absolute inset-0 z-10 size-full"
        aria-hidden
      />
      <canvas
        ref={captionCanvasRef}
        className="pointer-events-none absolute inset-0 z-10 size-full"
        aria-hidden
      />
    </>
  );
}

export default LibassLayer;
