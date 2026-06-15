import type { HookOverlay } from "@/lib/types";

// ────────────────────────────────────────────────────────────────────────────
// Хук-пресеты — отдельная галерея «look'ов» заголовка (как Submagic hookTitle /
// OpusClip title-presets: §6 спека). НЕ caption-пресеты: те про пословное караоке,
// к одиночному заголовку не мапятся. Каждый — Partial<HookOverlay> (только стиль +
// анимация входа), применяется через существующий onHookChange (мерж поверх хука):
// НЕ трогает text/enabled/full_clip/duration и — по правилу фаундера «пресет не
// двигает позицию» — НЕ задаёт margin_v (сохраняем ручную позицию хука).
// ────────────────────────────────────────────────────────────────────────────

export interface HookPreset {
  id: string;
  name: string;
  values: Partial<HookOverlay>;
}

export const HOOK_PRESETS: HookPreset[] = [
  {
    id: "coral_pill",
    name: "Coral pill",
    values: {
      font: "Unbounded",
      size: 64,
      color: "#FFFFFF",
      box_color: "#FF5A3D",
      box_opacity: 1,
      outline_w: 0,
      shadow: 0,
      uppercase: true,
      animation: "pop",
    },
  },
  {
    id: "bold_outline",
    name: "Bold outline",
    values: {
      font: "Unbounded",
      size: 76,
      color: "#FFFFFF",
      box_color: null,
      outline_color: "#000000",
      outline_w: 8,
      shadow: 0,
      uppercase: true,
      animation: "pop",
    },
  },
  {
    id: "clean",
    name: "Clean",
    values: {
      font: "Montserrat",
      size: 60,
      color: "#FFFFFF",
      box_color: null,
      outline_color: "#000000",
      outline_w: 4,
      shadow: 2,
      uppercase: true,
      animation: "fade",
    },
  },
  {
    id: "yellow_pop",
    name: "Yellow pop",
    values: {
      font: "Unbounded",
      size: 72,
      color: "#FFE000",
      box_color: null,
      outline_color: "#000000",
      outline_w: 6,
      shadow: 0,
      uppercase: true,
      animation: "bounce",
    },
  },
  {
    id: "minimal",
    name: "Minimal",
    values: {
      font: "Montserrat",
      size: 54,
      color: "#FFFFFF",
      box_color: null,
      outline_color: "#000000",
      outline_w: 0,
      shadow: 3,
      uppercase: false,
      animation: "none",
    },
  },
];
