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
  // UI-шрифты без bold-ката
  "Unbounded",
  "Anton",
  "Archivo Black",
  "Bebas Neue",
  "Luckiest Guy",
  "Poppins",
  "Russo One",
  // кириллице-способные look-match'ы (тяжёлые статик-инстансы, subfamily "Regular"); "Rubik"
  // здесь НЕТ (его TTF — Bold-кат, Bold=-1). Зеркало captions_v2.py.
  "Rubik Black",
  "Play",
  "Oswald Heavy",
  "Oswald",
  "Inter",
  "Nunito Black",
]);

/** ASS Bold-флаг: 0 для single-weight шрифтов (без fake-bold), иначе -1. Зеркало `_ass_bold_flag`. */
function assBoldFlag(font: string): number {
  return SINGLE_WEIGHT_FONTS.has(font) ? 0 : -1;
}

// ── Font-swap для покрытия глифов (зеркало captions_v2.py resolve_font_for_text) ──
// БЕЗ этого превью расходится с рендером: воркер свапает ВЕСЬ текст на Montserrat, а
// libass-превью (per-glyph fallbackFont) рисовал бы смешанный Unbounded+Montserrat.
// Шрифты БЕЗ кириллицы вовсе (Latin-only). Зеркало LATIN_ONLY_FONTS.
const LATIN_ONLY_FONTS = new Set([
  "Anton",
  "Archivo Black",
  "Bebas Neue",
  "Luckiest Guy",
  "Poppins",
]);
// Шрифты с русской кириллицей, но БЕЗ казахских глифов (→ tofu на казахском). Unbounded =
// дефолт хука, Russo One = пресет «u». Зеркало KAZAKH_INCOMPLETE_FONTS.
const KAZAKH_INCOMPLETE_FONTS = new Set(["Unbounded", "Russo One"]);
// Последний резерв — только для шрифтов БЕЗ записи в LOOK_MATCH_FOR_CYRILLIC.
const CYRILLIC_FALLBACK_FONT = "Montserrat";
// Кириллице-способный LOOK-match на каждый display-слот: сохраняет жирный лук на кириллице/
// казахском вместо отката в Montserrat. Каждый таргет покрывает все 18 казахских глифов +
// русский и подобран под лук оригинала (OFL). Зеркало LOOK_MATCH_FOR_CYRILLIC в captions_v2.py.
const LOOK_MATCH_FOR_CYRILLIC: Record<string, string> = {
  Unbounded: "Rubik Black", // дефолт хука: геометрический ультра-болд
  "Russo One": "Play", // пресет «u» Gamer Tech: квадратный техно
  Anton: "Oswald Heavy", // пресет «n»: высокий узкий жирный
  "Bebas Neue": "Oswald", // пресет «q»: высокий узкий капс
  "Archivo Black": "Inter", // пресет «o»: гротеск-блэк
  "Luckiest Guy": "Nunito Black", // пресет «t» Sticker Round: круглый
  Poppins: "Rubik", // пресет «p» Bold Pop White: геометрический болд
};
// 18 казахо-уникальных кодпойнтов (9 букв × 2 регистра). Зеркало KAZAKH_CODEPOINTS.
const KAZAKH_CODEPOINTS = new Set([
  0x04d9, 0x04d8, 0x0493, 0x0492, 0x049b, 0x049a, 0x04a3, 0x04a2, 0x04e9, 0x04e8, 0x04b1, 0x04b0,
  0x04af, 0x04ae, 0x0456, 0x0406, 0x04bb, 0x04ba,
]);

/** True если в тексте есть кириллица U+0400–U+04FF. Зеркало `_has_cyrillic`. */
function hasCyrillic(text: string): boolean {
  for (const ch of text) {
    const c = ch.codePointAt(0);
    if (c !== undefined && c >= 0x0400 && c <= 0x04ff) return true;
  }
  return false;
}

/** True если в тексте есть казахо-уникальный кодпойнт. Зеркало `_has_kazakh`. */
function hasKazakh(text: string): boolean {
  for (const ch of text) {
    const c = ch.codePointAt(0);
    if (c !== undefined && KAZAKH_CODEPOINTS.has(c)) return true;
  }
  return false;
}

/**
 * Подобрать шрифт под текст (зеркало `resolve_font_for_text`). Латиница → шрифт не трогаем.
 * Кириллица: (1) есть запись в LOOK_MATCH_FOR_CYRILLIC → кириллице-способный аналог,
 * сохраняющий жирный лук (применяется ко ВСЕЙ кириллице, русский тоже); (2) иначе фолбэк —
 * Latin-only → Montserrat, Kazakh-incomplete → Montserrat только при казахском глифе. Делает
 * превью libass пиксель-в-пиксель равным baked-рендеру воркера (WYSIWYG).
 */
export function resolveFontForText(font: string, text: string): string {
  if (!hasCyrillic(text)) return font;
  const look = LOOK_MATCH_FOR_CYRILLIC[font];
  if (look !== undefined) return look;
  if (LATIN_ONLY_FONTS.has(font)) return CYRILLIC_FALLBACK_FONT;
  if (KAZAKH_INCOMPLETE_FONTS.has(font) && hasKazakh(text)) return CYRILLIC_FALLBACK_FONT;
  return font;
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

// Ширина блока (wrap_width, доля PlayResX) → симметричные MarginL=MarginR. libass переносит
// текст внутри `PlayResX - L - R` → блок сужается, шрифт не меняется (#2). None = дефолт.
// Зеркало `_wrap_margins` (captions_v2.py): side = round((play_w - round(wrap*play_w))/2).
function wrapMargins(
  wrapWidth: number | null | undefined,
  playW: number,
  def: number,
): [number, number] {
  if (wrapWidth == null) return [def, def];
  const side = Math.round((playW - Math.round(wrapWidth * playW)) / 2);
  return [side, side];
}

// Свободная позиция X/Y → ведущий override-блок `\pos(x,y)\anN` на Dialogue (#3). Зеркало
// `_pos_override`: x = round((pos_x ?? 0.5)·play_w); y = pos_y задан ? round(pos_y·play_h) :
// legacyY (caption: play_h − margin_v под \an2; hook: margin_v под \an8). Пусто если оба None.
function posOverride(
  posX: number | null | undefined,
  posY: number | null | undefined,
  anchor: 2 | 8,
  playW: number,
  playH: number,
  legacyY: number,
): string {
  if (posX == null && posY == null) return "";
  const x = Math.round((posX ?? 0.5) * playW);
  const y = posY != null ? Math.round(posY * playH) : legacyY;
  return `\\pos(${x},${y})\\an${anchor}`;
}

/** Строка `Style: Default,…` из style+highlight (+wrap_width). Зеркало compile_ass (без \n).
 *  `text` = совокупный текст субтитров — для font-swap (казахский/кириллица → Montserrat). */
export function buildDefaultStyleLine(
  style: CaptionStyle,
  highlight: HighlightStyle | null | undefined,
  playW = 1080,
  text = "",
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
  // Шрифт-свап по тексту (зеркало compile_ass): bold-флаг считаем по РАЗРЕШЁННОМУ шрифте.
  const font = resolveFontForText(style.font ?? S.font, text);
  const [ml, mr] = wrapMargins(style.wrap_width, playW, 40);
  return (
    `Style: Default,${font},${style.size ?? S.size},${primary},${secondary},` +
    // Bold=0 для single-weight шрифтов — иначе прожиг подменит семейство (зеркало captions_v2).
    `${outline},${back},${assBoldFlag(font)},0,0,0,100,100,0,0,${borderStyle},${style.outline_w ?? S.outline_w},` +
    `${style.shadow ?? S.shadow},${style.alignment ?? S.alignment},${ml},${mr},${style.margin_v ?? S.margin_v},1`
  );
}

/** Строка `Style: Hook,…` из hook (+wrap_width). Зеркало build_hook_event style-строки (без \n).
 *  `text` = текст хука — для font-swap (казахский/кириллица → Montserrat). По умолчанию hook.text. */
export function buildHookStyleLine(hook: HookOverlay, playW = 1080, text?: string): string {
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
  // Шрифт-свап по тексту хука (зеркало build_hook_event); bold-флаг — по РАЗРЕШЁННОМУ шрифте.
  const font = resolveFontForText(hook.font ?? H.font, text ?? hook.text ?? "");
  const [ml, mr] = wrapMargins(hook.wrap_width, playW, 60);
  return (
    `Style: Hook,${font},${hook.size ?? H.size},${primary},${primary},` +
    `${outline},${back},${assBoldFlag(font)},0,0,0,100,100,0,0,${borderStyle},${outlineW},${hook.shadow ?? H.shadow},` +
    `8,${ml},${mr},${hook.margin_v ?? H.margin_v},1`
  );
}

/** Целое из `PlayResX:`/`PlayResY:` в ASS (дефолт 9:16 1080×1920). */
function playRes(ass: string): [number, number] {
  const w = Number.parseInt(ass.match(/PlayResX:\s*(\d+)/)?.[1] ?? "1080", 10);
  const h = Number.parseInt(ass.match(/PlayResY:\s*(\d+)/)?.[1] ?? "1920", 10);
  return [w, h];
}

/** Имя стиля Dialogue-строки (4-е поле) или "". */
function dialogueStyle(line: string): string {
  // Dialogue: Layer,Start,End,Style,Name,MarginL,MarginR,Effect,Text
  return line.split(",", 4)[3] ?? "";
}

/** Совокупный ТЕКСТ субтитров (Default Dialogue) из ASS — для font-swap по покрытию глифов.
 *  Снимаем override-блоки {…} (там только ASCII-теги), казахские кодпойнты живут лишь в тексте.
 *  Зеркалит compile_ass: font подбирается по тексту видимых реплик. */
function captionTextFromAss(ass: string): string {
  const parts: string[] = [];
  for (const line of ass.split("\n")) {
    if (!line.startsWith("Dialogue:") || dialogueStyle(line) !== "Default") continue;
    const m = line.match(/^Dialogue:(?:[^,]*,){8}([\s\S]*)$/);
    if (m) parts.push(m[1].replace(/\{[^}]*\}/g, ""));
  }
  return parts.join(" ");
}

/** Вписать наш ведущий `\pos`-блок в Text Dialogue-строки (caption \an2 / hook \an8). */
function applyPosToDialogue(line: string, pos: string): string {
  // отделяем 8 полей-префикс (до Text) от самого Text (Text может содержать запятые)
  const m = line.match(/^(Dialogue:(?:[^,]*,){8})([\s\S]*)$/);
  if (!m) return line;
  const prefix = m[1];
  let text = m[2];
  const isHook = dialogueStyle(line) === "Hook";
  if (isHook) {
    // у хука ведущий блок может уже нести entrance-анимацию (\fscy/\t…) И/ИЛИ наш \pos.
    // Снимаем ТОЛЬКО свой \pos\an, сохраняя entrance, потом дописываем новый \pos впереди.
    const bm = text.match(/^\{([^}]*)\}([\s\S]*)$/);
    let entrance = "";
    let rest = text;
    if (bm) {
      entrance = bm[1].replace(/^\\pos\([^)]*\)/, "").replace(/^\\an\d/, "");
      rest = bm[2];
    }
    const content = (pos ? pos : "") + entrance;
    text = content ? `{${content}}${rest}` : rest;
  } else {
    // caption: первый блок — пословный {\k…}; наш \pos идёт ОТДЕЛЬНЫМ блоком впереди него.
    text = text.replace(/^\{\\pos\([^)]*\)\\an\d\}/, ""); // снять прежнюю нашу инъекцию
    if (pos) text = `{${pos}}${text}`;
  }
  return prefix + text;
}

/**
 * Переписать `Style: Default,…`/`Style: Hook,…` И ведущие `\pos`-блоки Dialogue-строк в
 * ASS-тексте из текущих style/highlight/hook — для МГНОВЕННОГО libass-превью (WYSIWYG).
 *
 * Покрывает Style-строку (шрифт/размер/цвет/контур/плашка/позиция/ШИРИНА блока via margins)
 * И свободную позицию X/Y (через `\pos` на Dialogue). Заменяет ТОЛЬКО уже существующие
 * Style-строки/Dialogue. Если хук только что включили и Hook-строки в серверном ASS ещё нет —
 * НЕ синтезируем (нужны Dialogue+окно): добирает дебаунс-PATCH. Сервер остаётся источником
 * правды (экспорт ВСЕГДА из Python-ASS → дрейфа на экспорте нет). Идемпотентно.
 */
export function patchAssStyles(
  ass: string,
  style: CaptionStyle,
  highlight: HighlightStyle | null | undefined,
  hook: HookOverlay | null | undefined,
): string {
  if (!ass) return ass;
  const [playW, playH] = playRes(ass);
  // Текст для font-swap: субтитры берём из ASS Default Dialogue, хук — из hook.text.
  const capText = captionTextFromAss(ass);
  const hookText = hook?.text ?? "";
  const defaultLine = buildDefaultStyleLine(style, highlight, playW, capText);
  const capPos = posOverride(
    style.pos_x,
    style.pos_y,
    2,
    playW,
    playH,
    playH - (style.margin_v ?? S.margin_v),
  );
  const hookPos = hook
    ? posOverride(hook.pos_x, hook.pos_y, 8, playW, playH, hook.margin_v ?? H.margin_v)
    : "";
  const lines = ass.split("\n").map((line) => {
    if (line.startsWith("Style: Default,")) return defaultLine;
    if (hook && line.startsWith("Style: Hook,")) return buildHookStyleLine(hook, playW, hookText);
    if (line.startsWith("Dialogue:")) {
      const st = dialogueStyle(line);
      if (st === "Default") return applyPosToDialogue(line, capPos);
      if (hook && st === "Hook") return applyPosToDialogue(line, hookPos);
    }
    return line;
  });
  return lines.join("\n");
}
