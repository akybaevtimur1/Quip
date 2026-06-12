"use client";

import { Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { ClipEdit, HookOverlay } from "@/lib/types";

// ── Таб «Хук»: топ-текст клипа (T1, наш отличитель — объяснимый цепляющий заголовок) ──
// Хук = ASS-событие с верхним якорем В ТОМ ЖЕ файле, что субтитры → libass-превью
// показывает его пиксель-в-пиксель как экспорт. Правки идут через patchCaptions
// (PATCH всего captions), как стиль/анимация → единая очередь мутаций, без 409.
// Поля HookOverlay все опциональны → создавая хук с нуля, шлём только text/enabled,
// pydantic дольёт дефолты (шрифт Unbounded, коралл-плашка, размер 66).

export function HookTab({
  edit,
  busy,
  onHookChange,
}: {
  edit: ClipEdit;
  busy: boolean;
  onHookChange: (patch: Partial<HookOverlay> | null) => void;
}) {
  const hook = edit.captions.hook ?? null;
  const enabled = hook?.enabled ?? false;
  const fullClip = hook?.full_clip ?? true;

  // локальный текст: печать не должна слать PATCH на каждый символ (как ColorField).
  // Коммит — на blur / Enter-pause (debounce). Синк с пропом — adjust-during-render.
  const [text, setText] = useState(hook?.text ?? "");
  const [prevText, setPrevText] = useState(hook?.text ?? "");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  if ((hook?.text ?? "") !== prevText) {
    setPrevText(hook?.text ?? "");
    setText(hook?.text ?? "");
  }
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const commitText = (value: string) => {
    setText(value);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => onHookChange({ text: value, enabled: true }), 350);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">
            Топ-текст (хук)
          </p>
          <label className="flex cursor-pointer items-center gap-2 text-xs text-muted">
            <input
              type="checkbox"
              checked={enabled}
              disabled={busy}
              onChange={(e) =>
                onHookChange(e.target.checked ? { enabled: true } : { enabled: false })
              }
              className="size-3.5 accent-accent"
            />
            Показывать
          </label>
        </div>

        <textarea
          value={text}
          disabled={busy}
          rows={2}
          maxLength={80}
          placeholder="Цепляющий заголовок сверху клипа…"
          onChange={(e) => commitText(e.target.value)}
          onBlur={() => {
            if (timer.current) clearTimeout(timer.current);
            onHookChange({ text, enabled: text.trim() ? true : enabled });
          }}
          className="w-full resize-none rounded-xl border border-line bg-surface-2 px-3 py-2 text-sm font-semibold text-ink outline-none focus:ring-2 focus:ring-accent/40"
        />
        <p className="flex items-center gap-1.5 text-[11px] leading-snug text-muted">
          <Sparkles className="size-3 shrink-0 text-accent" />
          Короткий заголовок (≤6 слов), привязанный к сути момента. Останавливает скролл.
        </p>
      </section>

      <section className="space-y-2">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">
          Когда показывать
        </p>
        <div className="grid grid-cols-2 gap-1.5">
          <button
            type="button"
            disabled={busy}
            onClick={() => onHookChange({ full_clip: true })}
            className={`rounded-xl border px-3 py-2.5 text-sm font-semibold transition ${
              fullClip
                ? "border-accent/60 bg-accent/10 text-accent"
                : "border-line bg-surface-2 text-muted hover:border-accent/30"
            }`}
          >
            Весь клип
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => onHookChange({ full_clip: false })}
            className={`rounded-xl border px-3 py-2.5 text-sm font-semibold transition ${
              !fullClip
                ? "border-accent/60 bg-accent/10 text-accent"
                : "border-line bg-surface-2 text-muted hover:border-accent/30"
            }`}
          >
            Первые секунды
          </button>
        </div>
        {!fullClip && (
          <label className="flex flex-col gap-1 pt-1 text-xs text-muted">
            <span className="flex items-center justify-between">
              Длительность показа
              <span className="font-mono text-[11px] text-ink">
                {(hook?.duration_sec ?? 4).toFixed(0)} с
              </span>
            </span>
            <input
              type="range"
              min={1}
              max={15}
              value={Math.round(hook?.duration_sec ?? 4)}
              disabled={busy}
              onChange={(e) => onHookChange({ duration_sec: Number(e.target.value) })}
              className="h-1.5 cursor-pointer appearance-none rounded-full bg-surface-2 accent-accent"
            />
          </label>
        )}
      </section>

      {hook && (
        <button
          type="button"
          disabled={busy}
          onClick={() => onHookChange(null)}
          className="self-start text-xs text-muted underline-offset-2 transition hover:text-red-400 hover:underline"
        >
          Убрать хук
        </button>
      )}
    </div>
  );
}
