"use client";

import { useEffect, useRef } from "react";
import type SubtitlesOctopus from "libass-wasm";

// ────────────────────────────────────────────────────────────────────────────
// LibassLayer — тонкая обёртка SubtitlesOctopus (libass.wasm, MIT).
// Рисует ТОТ ЖЕ ASS, что жжёт ffmpeg на экспорте → превью субтитров =
// экспорт пиксель-в-пиксель. SubtitlesOctopus сам создаёт <canvas> рядом с
// видео (sibling в его родителе) и синхронит по video.currentTime + timeOffset.
//
// ASS — в КЛИП-времени (0-based), видео в превью = source.mp4 в SOURCE-времени,
// поэтому timeOffset = -sourceStart выравнивает: при source-времени T реплика
// показывается на клип-времени T − sourceStart. Сеттера timeOffset нет → смена
// sourceStart пересоздаёт инстанс (ниже — в deps эффекта).
//
// Ничего видимого сам не рендерит (canvas вставляет октопус). При ошибке НЕ
// кидает — зовёт props.onError, чтобы родитель показал CSS-фолбэк CaptionOverlay.
// ────────────────────────────────────────────────────────────────────────────

interface LibassLayerProps {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  assText: string;
  sourceStart: number;
  onError?: () => void;
}

export function LibassLayer({ videoRef, assText, sourceStart, onError }: LibassLayerProps) {
  const instanceRef = useRef<SubtitlesOctopus | null>(null);
  // assText держим в ref, чтобы эффект создания инстанса не зависел от assText
  // (иначе каждая правка пересоздавала бы тяжёлый WASM-инстанс). Отдельный
  // эффект ниже зовёт setTrack на живом инстансе. Синк ref'ов — в эффекте
  // (правило react-hooks/refs: не писать ref во время рендера).
  const assRef = useRef(assText);
  const onErrorRef = useRef(onError);
  useEffect(() => {
    assRef.current = assText;
    onErrorRef.current = onError;
  });

  // ── создание / пересоздание инстанса (deps: видео-узел + sourceStart) ──
  // sourceStart в deps: timeOffset задаётся ТОЛЬКО в конструкторе, сеттера нет.
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !assRef.current) return;

    let disposed = false;
    let local: SubtitlesOctopus | null = null;

    (async () => {
      try {
        const SubtitlesOctopus = (await import("libass-wasm")).default;
        // эффект мог размонтироваться, пока грузился чанк/WASM
        if (disposed) return;
        local = new SubtitlesOctopus({
          video,
          subContent: assRef.current,
          workerUrl: "/libass/subtitles-octopus-worker.js",
          legacyWorkerUrl: "/libass/subtitles-octopus-worker-legacy.js",
          // тот же набор, что у ffmpeg-экспорта (services/worker/fonts) — WYSIWYG
          fonts: [
            "/libass/fonts/Montserrat.ttf",
            "/libass/fonts/Unbounded.ttf",
            "/libass/fonts/Rubik.ttf",
          ],
          timeOffset: -sourceStart,
          onError: () => onErrorRef.current?.(),
        });
        instanceRef.current = local;
      } catch {
        // инициализация/импорт упали → деградация на CSS-фолбэк, без throw
        if (!disposed) onErrorRef.current?.();
      }
    })();

    return () => {
      disposed = true;
      // disposi'м тот инстанс, что реально создали (local), и чистим ref если он наш
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
  }, [videoRef, sourceStart]);

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

  return null;
}

export default LibassLayer;
