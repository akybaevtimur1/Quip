"use client";

import { useEffect, useRef } from "react";
import type SubtitlesOctopus from "libass-wasm";

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
// При ошибке НЕ кидает — зовёт props.onError, родитель показывает CSS-фолбэк.
// ────────────────────────────────────────────────────────────────────────────

interface LibassLayerProps {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  assText: string;
  sourceStart: number;
  onError?: () => void;
}

export function LibassLayer({ videoRef, assText, sourceStart, onError }: LibassLayerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const instanceRef = useRef<SubtitlesOctopus | null>(null);
  // ref'ы вместо deps: правки ASS/интервала не должны пересоздавать WASM-инстанс
  const assRef = useRef(assText);
  const startRef = useRef(sourceStart);
  const onErrorRef = useRef(onError);
  useEffect(() => {
    assRef.current = assText;
    startRef.current = sourceStart;
    onErrorRef.current = onError;
  });

  // ── создание инстанса (один раз на mount) + размер + rAF-синк времени ──
  useEffect(() => {
    const canvas = canvasRef.current;
    const video = videoRef.current;
    if (!canvas || !video || !assRef.current) return;

    let disposed = false;
    let local: SubtitlesOctopus | null = null;
    let raf = 0;
    let ro: ResizeObserver | null = null;

    (async () => {
      try {
        const SubtitlesOctopusCtor = (await import("libass-wasm")).default;
        if (disposed) return;
        local = new SubtitlesOctopusCtor({
          canvas,
          subContent: assRef.current,
          workerUrl: "/libass/subtitles-octopus-worker.js",
          legacyWorkerUrl: "/libass/subtitles-octopus-worker-legacy.js",
          // тот же набор, что у ffmpeg-экспорта (services/worker/fonts) — WYSIWYG
          fonts: [
            "/libass/fonts/Montserrat.ttf",
            "/libass/fonts/Unbounded.ttf",
            "/libass/fonts/Rubik.ttf",
          ],
          // дефолтный fallback = default.woff2 РЯДОМ С ВОРКЕРОМ — мы его не хостим,
          // воркер падал «Loading data file default.woff2 failed» → тихий CSS-фолбэк.
          // Наш fallback — Montserrat (есть кириллица), файл хостится.
          fallbackFont: "/libass/fonts/Montserrat.ttf",
          onError: (e?: unknown) => {
            // внятный лог вместо «Worker error: {}» (ErrorEvent не сериализуется)
            const msg =
              e instanceof ErrorEvent ? e.message : e instanceof Error ? e.message : String(e);
            console.error("[libass] init/worker error:", msg || "(без деталей)");
            onErrorRef.current?.();
          },
        });
        instanceRef.current = local;

        // размер канваса = размер контейнера (CSS-пиксели × DPR)
        const applySize = () => {
          const box = canvas.parentElement;
          if (!box || !local) return;
          const r = box.getBoundingClientRect();
          const dpr = window.devicePixelRatio || 1;
          const w = Math.max(1, Math.round(r.width * dpr));
          const h = Math.max(1, Math.round(r.height * dpr));
          try {
            local.resize(w, h);
          } catch {
            /* инстанс мог умереть — onError уже сработал */
          }
        };
        applySize();
        ro = new ResizeObserver(applySize);
        if (canvas.parentElement) ro.observe(canvas.parentElement);

        // время: ASS в клип-времени, видео в source-времени
        let lastT = -1;
        const tick = () => {
          if (disposed) return;
          const t = Math.max(0, video.currentTime - startRef.current);
          if (Math.abs(t - lastT) > 0.01 && local) {
            lastT = t;
            try {
              local.setCurrentTime(t);
            } catch {
              /* noop */
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
      const inst = local ?? instanceRef.current;
      if (inst) {
        try {
          inst.dispose();
        } catch {
          /* dispose не должен ронять размонтирование */
        }
      }
      if (instanceRef.current === local) instanceRef.current = null;
    };
  }, [videoRef]);

  // ── живое обновление трека при смене assText (БЕЗ пересоздания) ──
  useEffect(() => {
    const inst = instanceRef.current;
    if (!inst || !assText) return;
    try {
      inst.setTrack(assText);
    } catch {
      onErrorRef.current?.();
    }
  }, [assText]);

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none absolute inset-0 z-10 size-full"
      aria-hidden
    />
  );
}

export default LibassLayer;
