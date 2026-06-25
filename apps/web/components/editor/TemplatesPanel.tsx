"use client";

import { Check, Plus, RefreshCw, Star, Trash2 } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { IconButton } from "@/components/ui/IconButton";
import type { StylePreferencePayload, StyleTemplate } from "@/lib/api";

// ────────────────────────────────────────────────────────────────────────────
// TemplatesPanel — the "Style templates" surface, lifted OUT of the Subtitles tab
// into a GLOBAL header popover (ClipEditorScreen → EditorHeader). A style template
// is a cross-panel action over the WHOLE look (captions + highlight + hook style +
// position/size + hook timing — founder 2026-06-25: a template remembers EVERYTHING),
// so it belongs above the 4 editing tabs, not buried inside one of them.
//
// Self-contained: owns ONLY its local UI state (the name draft, a per-action busy
// key, a transient confirmation toast). All real wiring (apply/save/delete/default)
// lives in ClipEditorScreen and arrives via props — this is purely the render
// location + the small UI affordances around those handlers.
// ────────────────────────────────────────────────────────────────────────────

export function TemplatesPanel({
  templates,
  defaultTemplateId,
  busy,
  onError,
  onApplyTemplateClip,
  onApplyTemplateAll,
  onSaveTemplate,
  onUpdateTemplate,
  onDeleteTemplate,
  onSetDefaultTemplate,
}: {
  /** The user's saved style templates + which one seeds new clips of future videos. */
  templates: StyleTemplate[];
  defaultTemplateId: string | null;
  /** Heavy ops (render/save) in flight → disable apply/save actions. */
  busy: boolean;
  onError: (msg: string) => void;
  /** Apply a template's look to THIS clip (instant). */
  onApplyTemplateClip: (look: StylePreferencePayload) => void;
  /** Apply a template to ALL clips (instant on this one, rest in background) → count. */
  onApplyTemplateAll: (look: StylePreferencePayload) => Promise<number>;
  /** Save the current look as a NAMED template (optionally the new-clip default). */
  onSaveTemplate: (name: string, setDefault: boolean) => Promise<void>;
  /** Overwrite an existing template's stored look with the CURRENT clip style (update in place). */
  onUpdateTemplate: (id: string) => Promise<void>;
  onDeleteTemplate: (id: string) => Promise<void>;
  onSetDefaultTemplate: (id: string, isDefault: boolean) => Promise<void>;
}) {
  // Own busy keyed by action (no global busy → other rows stay live) + transient toast.
  const [tplBusy, setTplBusy] = useState<string | null>(null);
  const [tplMsg, setTplMsg] = useState<string | null>(null);
  const [newName, setNewName] = useState("");

  const flashTpl = (msg: string) => {
    setTplMsg(msg);
    setTimeout(() => setTplMsg(null), 3000);
  };

  const applyToClip = (t: StyleTemplate) => {
    onApplyTemplateClip(t.look);
    flashTpl(`Applied “${t.name}” to this clip`);
  };

  const applyToAll = async (t: StyleTemplate) => {
    setTplBusy(`all:${t.id}`);
    try {
      const n = await onApplyTemplateAll(t.look);
      flashTpl(`Applied “${t.name}” to ${n} clip${n === 1 ? "" : "s"}`);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Couldn’t apply to all clips");
    } finally {
      setTplBusy(null);
    }
  };

  const saveCurrent = async () => {
    setTplBusy("save");
    try {
      await onSaveTemplate(newName.trim() || `My style ${templates.length + 1}`, false);
      setNewName("");
      flashTpl("Template saved");
    } catch (e) {
      onError(e instanceof Error ? e.message : "Couldn’t save the template");
    } finally {
      setTplBusy(null);
    }
  };

  // Overwrite this template's saved look with the CURRENT clip style (update in place — no
  // delete + re-add). Same save path as "Save current", just keyed to this template's id.
  const updateTpl = async (t: StyleTemplate) => {
    setTplBusy(`upd:${t.id}`);
    try {
      await onUpdateTemplate(t.id);
      flashTpl(`Updated “${t.name}” to the current style`);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Couldn’t update the template");
    } finally {
      setTplBusy(null);
    }
  };

  const removeTpl = async (t: StyleTemplate) => {
    setTplBusy(`del:${t.id}`);
    try {
      await onDeleteTemplate(t.id);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Couldn’t delete the template");
    } finally {
      setTplBusy(null);
    }
  };

  const toggleDefault = async (t: StyleTemplate) => {
    setTplBusy(`def:${t.id}`);
    try {
      await onSetDefaultTemplate(t.id, defaultTemplateId !== t.id);
      flashTpl(
        defaultTemplateId === t.id
          ? "No longer your default"
          : `“${t.name}” will start new videos`,
      );
    } catch (e) {
      onError(e instanceof Error ? e.message : "Couldn’t set default");
    } finally {
      setTplBusy(null);
    }
  };

  return (
    <section className="space-y-2.5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex flex-col">
          <h3 className="text-sm font-semibold text-ink">Style templates</h3>
          <p className="text-xs leading-snug text-muted">
            Reuse a whole look — colors, fonts, position, size and the hook — on any clip.
          </p>
        </div>
        {tplMsg && <span className="truncate text-xs font-medium text-ok">{tplMsg}</span>}
      </div>

      {templates.length === 0 ? (
        <p className="text-xs leading-snug text-muted">
          Save the current look as a template, then reuse it on any clip — or apply it to a
          whole video in one click. Star one to start every new video with it.
        </p>
      ) : (
        <div className="space-y-1.5">
          {templates.map((t) => {
            const isDefault = defaultTemplateId === t.id;
            const swatch = (t.look.style?.color as string) ?? "#ffffff";
            const hi = (t.look.highlight?.color as string | undefined) ?? null;
            const busyAll = tplBusy === `all:${t.id}`;
            const busyUpd = tplBusy === `upd:${t.id}`;
            return (
              <div
                key={t.id}
                className="flex items-center gap-2 rounded-md border border-line bg-surface-2 px-2.5 py-2"
              >
                <span className="flex shrink-0 items-center -space-x-1">
                  <span
                    className="size-3.5 rounded-full ring-1 ring-line"
                    style={{ background: swatch }}
                  />
                  {hi && (
                    <span
                      className="size-3.5 rounded-full ring-1 ring-line"
                      style={{ background: hi }}
                    />
                  )}
                </span>
                <button
                  type="button"
                  onClick={() => applyToClip(t)}
                  disabled={busy}
                  title="Apply to this clip"
                  className="min-w-0 flex-1 truncate text-left text-xs font-semibold text-ink transition hover:text-accent disabled:opacity-50"
                >
                  {t.name}
                  {isDefault && (
                    <Badge tone="neutral" className="ml-1.5 align-middle">
                      default
                    </Badge>
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => void applyToAll(t)}
                  disabled={busy || tplBusy !== null}
                  title="Apply to ALL clips of this video"
                  className="shrink-0 rounded border border-line px-2 py-1 text-xs font-semibold text-muted transition duration-150 ease-snappy enabled:hover:border-line-strong enabled:hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-50"
                >
                  {busyAll ? "Applying…" : "All clips"}
                </button>
                <button
                  type="button"
                  onClick={() => void updateTpl(t)}
                  disabled={busy || tplBusy !== null}
                  title="Update — overwrite this template with the current clip’s style"
                  className="inline-flex shrink-0 items-center gap-1 rounded border border-line px-2 py-1 text-xs font-semibold text-muted transition duration-150 ease-snappy enabled:hover:border-line-strong enabled:hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-50"
                >
                  <RefreshCw className={`size-3 ${busyUpd ? "animate-spin" : ""}`} aria-hidden />
                  {busyUpd ? "Updating…" : "Update"}
                </button>
                <IconButton
                  size="sm"
                  tone="accent"
                  title={
                    isDefault
                      ? "Default for new videos (click to unset)"
                      : "Use for new videos"
                  }
                  aria-label="Toggle default template"
                  disabled={tplBusy !== null}
                  onClick={() => void toggleDefault(t)}
                >
                  <Star className={`size-3.5 ${isDefault ? "fill-current" : ""}`} />
                </IconButton>
                <IconButton
                  size="sm"
                  tone="danger"
                  title="Delete template"
                  aria-label="Delete template"
                  disabled={tplBusy !== null}
                  onClick={() => void removeTpl(t)}
                >
                  <Trash2 className="size-3.5" />
                </IconButton>
              </div>
            );
          })}
        </div>
      )}

      <div className="flex items-center gap-2">
        <input
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="Name this style…"
          maxLength={60}
          onKeyDown={(e) => {
            if (e.key === "Enter") void saveCurrent();
          }}
          className="min-w-0 flex-1 rounded-md border border-line bg-surface-2 px-2.5 py-1.5 text-xs text-ink outline-none transition focus:border-accent/60"
        />
        <button
          type="button"
          onClick={() => void saveCurrent()}
          disabled={busy || tplBusy !== null}
          className="inline-flex shrink-0 items-center gap-1 rounded-md border border-line bg-surface-2 px-2.5 py-1.5 text-xs font-semibold text-muted transition duration-150 ease-snappy enabled:hover:border-line-strong enabled:hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-50"
        >
          {tplBusy === "save" ? (
            <Check className="size-3.5 text-ok" />
          ) : (
            <Plus className="size-3.5" />
          )}
          Save current
        </button>
      </div>
    </section>
  );
}
