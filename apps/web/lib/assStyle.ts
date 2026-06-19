// ────────────────────────────────────────────────────────────────────────────
// assStyle — мгновенный превью стиля субтитров/хука БЕЗ серверного раунд-трипа.
//
// Берёт ПОСЛЕДНИЙ серверный ASS и переписывает ТОЛЬКО строки `Style: Default,…`
// и `Style: Hook,…` из текущих style/highlight/hook. Формат ТОЧНО зеркалит Python
// `compile_ass`/`build_hook_event` (services/worker/app/editor/captions_v2.py).
//
// ⚠️ Это ТРАНЗИЕНТ: сервер остаётся источником правды — авторитетный ASS приезжает
// дебаунс-PATCH'ем и перетирает локальный патч (реконсиляция). Экспорт ВСЕГДА из
// Python-ASS → дрейф на экспорте невозможен (см. spec B-#4). Поэтому покрываем
// только Style-строку (цвет/размер/шрифт/контур/тень/плашка/позиция); правки,
// меняющие Dialogue-теги (highlight-цвет, анимация субтитров, emphasis, UPPERCASE)
// — идут на сервер (редкие, не драг → не лагают).
// ────────────────────────────────────────────────────────────────────────────

import type { CaptionStyle, HighlightStyle, HookOverlay } from "@/lib/types";

// CaptionStyle-дефолты (зеркало models.py CaptionStyle) — TS-поля опциональны
// (pydantic default → не required в схеме), поэтому подставляем те же значения.
const S = {
  font: "Montserrat",
  size: 90,
  color: "#FFFFFF",
  outline_color: "#000000",
  outline_w: 6,
  shadow: 2,
  box_opacity: 0,
  margin_v: 260,
  alignment: 2,
};

// HookOverlay-дефолты (зеркало models.py HookOverlay).
const H = {
  font: "Unbounded",
  size: 66,
  color: "#FFFFFF",
  outline_color: "#000000",
  outline_w: 4,
  shadow: 0,
  box_color: "#FF5A3D" as string | null,
  box_opacity: 1,
  margin_v: 150,
};

// Шрифты БЕЗ реального bold-начертания (single-weight TTF) → Bold=0 в ASS-Style, иначе
// libass подменяет семейство (fake-bold). Зеркало SINGLE_WEIGHT_FONTS в captions_v2.py.
const SINGLE_WEIGHT_FONTS = new Set([
  "Unbounded",
  "Anton",
  "Archivo Black",
  "Bebas Neue",
  "Luckiest Guy",
  "Poppins",
  "Russo One",
]);

/** ASS Bold-флаг: 0 для single-weight шрифтов (без fake-bold), иначе -1. Зеркало `_ass_bold_flag`. */
function assBoldFlag(font: string): number {
  return SINGLE_WEIGHT_FONTS.has(font) ? 0 : -1;
}

/** #RRGGBB → ASS &HAABBGGRR (alphaByte: 0=непрозр., 255=прозр.). Зеркало `_ass_color`. */
export function assColor(hex: string, alphaByte = 0): string {
  const h = hex.replace(/^#/, "");
  const rr = h.slice(0, 2);
  const gg = h.slice(2, 4);
  const bb = h.slice(4, 6);
  const aa = alphaByte.toString(16).toUpperCase().padStart(2, "0");
  return `&H${aa}${bb}${gg}${rr}`.toUpperCase();
}

/** Строка `Style: Default,…` из style+highlight. Зеркало compile_ass (без \n). */
export function buildDefaultStyleLine(
  style: CaptionStyle,
  highlight: HighlightStyle | null | undefined,
): string {
  // animation="none" → караоке выключено целиком → primary = цвет текста (как в Python).
  const hl = highlight && highlight.animation !== "none" ? highlight : null;
  const primary = assColor(hl?.color ?? style.color ?? S.color);
  const secondary = assColor(style.color ?? S.color);
  const outline = assColor(style.outline_color ?? S.outline_color);
  let back: string;
  let borderStyle: number;
  if (style.box_color) {
    back = assColor(style.box_color, Math.round((1.0 - (style.box_opacity ?? S.box_opacity)) * 255));
    borderStyle = 3;
  } else {
    back = "&H64000000";
    borderStyle = 1;
  }
  return (
    `Style: Default,${style.font ?? S.font},${style.size ?? S.size},${primary},${secondary},` +
    // Bold=0 для single-weight шрифтов — иначе прожиг подменит семейство (зеркало captions_v2).
    `${outline},${back},${assBoldFlag(style.font ?? S.font)},0,0,0,100,100,0,0,${borderStyle},${style.outline_w ?? S.outline_w},` +
    `${style.shadow ?? S.shadow},${style.alignment ?? S.alignment},40,40,${style.margin_v ?? S.margin_v},1`
  );
}

/** Строка `Style: Hook,…` из hook. Зеркало build_hook_event style-строки (без \n). */
export function buildHookStyleLine(hook: HookOverlay): string {
  const primary = assColor(hook.color ?? H.color);
  let outline: string;
  let back: string;
  let borderStyle: number;
  let outlineW: number;
  const boxColor = hook.box_color === undefined ? H.box_color : hook.box_color;
  if (boxColor) {
    // libass BorderStyle=3 заливает плашку цветом OutlineColour (не BackColour).
    outline = assColor(boxColor, Math.round((1.0 - (hook.box_opacity ?? H.box_opacity)) * 255));
    back = "&H00000000";
    borderStyle = 3;
    outlineW = Math.max(hook.outline_w ?? H.outline_w, 6);
  } else {
    outline = assColor(hook.outline_color ?? H.outline_color);
    back = "&H64000000";
    borderStyle = 1;
    outlineW = hook.outline_w ?? H.outline_w;
  }
  return (
    `Style: Hook,${hook.font ?? H.font},${hook.size ?? H.size},${primary},${primary},` +
    `${outline},${back},${assBoldFlag(hook.font ?? H.font)},0,0,0,100,100,0,0,${borderStyle},${outlineW},${hook.shadow ?? H.shadow},` +
    `8,60,60,${hook.margin_v ?? H.margin_v},1`
  );
}

/**
 * Переписать `Style: Default,…` (и `Style: Hook,…`, если присутствует) в ASS-тексте
 * из текущих style/highlight/hook — для МГНОВЕННОГО libass-превью.
 *
 * Заменяет ТОЛЬКО уже существующие Style-строки (по префиксу). Если хук только что
 * включили и Hook-строки в серверном ASS ещё нет — НЕ синтезируем её здесь (нужны
 * Dialogue+окно): этот кейс добирает дебаунс-PATCH (это тогл, не драг). Возвращает
 * новый ASS; если совпадений нет — исходный (без падений).
 */
export function patchAssStyles(
  ass: string,
  style: CaptionStyle,
  highlight: HighlightStyle | null | undefined,
  hook: HookOverlay | null | undefined,
): string {
  if (!ass) return ass;
  const defaultLine = buildDefaultStyleLine(style, highlight);
  const lines = ass.split("\n").map((line) => {
    if (line.startsWith("Style: Default,")) return defaultLine;
    if (hook && line.startsWith("Style: Hook,")) return buildHookStyleLine(hook);
    return line;
  });
  return lines.join("\n");
}
