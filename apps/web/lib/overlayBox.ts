// ────────────────────────────────────────────────────────────────────────────
// overlayBox — чистая арифметика CapCut-рамки манипуляции (OverlaySelectionBox).
//
// Субтитры/хук libass-wasm рисует в логической сетке PlayResX=1080 × PlayResY=1920
// (services/worker/app/editor/captions_v2.py, lib/assStyle.ts). Текст ГОРИЗОНТАЛЬНО
// центрирован (нет поля горизонтальной позиции), wrap-ширина =
//   (1080 − 2·marginLR) логических px   (captions marginLR=40 → 1000; hook=60 → 960).
// Рендер-бокс на экране = offsetParent рамки (внутренний 9:16-бокс PreviewPlayer),
// CSS-размер W×H. Масштаб k = W/1080: экранный размер шрифта = size·k, экранная
// wrap-ширина = (1080 − 2·marginLR)·k.
//
// Эти функции — БЕЗ DOM (легко читать/ревьюить математику; у веба нет юнит-раннера,
// но вынос в чистые функции держит арифметику честной).
// ────────────────────────────────────────────────────────────────────────────

/** Логические ASS-единицы (база 1080) → экранные px при ширине рендер-бокса renderW. */
export function assUnitsToRenderPx(assValue: number, renderW: number): number {
  return (assValue * renderW) / 1080;
}

/**
 * Экранная wrap-ширина текста (px): (1080 − 2·marginLR) логических px, отмасштабированные
 * под рендер-бокс. marginLR — боковой отступ ASS (captions=40, hook=60).
 */
export function wrapWidthPx(marginLR: number, renderW: number): number {
  return assUnitsToRenderPx(1080 - 2 * marginLR, renderW);
}

/**
 * Из измеренных глиф-метрик текста (px на экране) → размер рамки в % рендер-бокса.
 * Добавляет равномерный паддинг padFrac·renderH с КАЖДОЙ стороны (px), затем переводит
 * в проценты. Клампится в [0..100].
 */
export function boxPctFromMetrics(
  textW: number,
  textH: number,
  renderW: number,
  renderH: number,
  padFrac: number,
): { widthPct: number; heightPct: number } {
  const padPx = padFrac * renderH;
  const wPx = textW + 2 * padPx;
  const hPx = textH + 2 * padPx;
  const widthPct = Math.min(100, Math.max(0, (wPx / renderW) * 100));
  const heightPct = Math.min(100, Math.max(0, (hPx / renderH) * 100));
  return { widthPct, heightPct };
}
