# 🌙 Night Audit — рой агентов-дебагеров (2026-06-15)

> Оркестратор раздаёт домены агентам-следователям/чинильщикам. Каждый агент владеет
> СТРОГО своим списком файлов (ownership) и пишет отчёт в `docs/night-audit/<domain>.md`.
> Агенты НЕ коммитят и НЕ трогают чужие файлы. Верификацию (`just check`) и коммиты
> делает ТОЛЬКО оркестратор, поволново.

## Железные правила для всех агентов
1. **Границы.** Редактируй ТОЛЬКО файлы из своего ownership-списка. Нашёл баг в чужом/
   общем файле — задокументируй в разделе «Передать оркестратору», НЕ правь.
2. **ОБЩИЕ ФАЙЛЫ — READ-ONLY для всех:** `services/worker/app/models.py`,
   `packages/shared/**`, `apps/web/components/ui/**`, `justfile`, `*.config.*`,
   `globals.css @theme`. Багу сюда → в отчёт оркестратору.
3. **Reframe/Render — инвариант.** Перед любой правкой `stage3_*`/`stage5_*`/`reframe_cache`
   ОБЯЗАТЕЛЬНО прочитай `docs/REFRAME_FPS_GRID_INVARIANT.md`. Кадровую сетку не менять.
   Только настоящие баги, с тестом, Δ=0 сохранить.
4. **TDD на pure-логике** (CLAUDE.md правило 3): сначала падающий тест, потом фикс.
5. **Никаких `except: pass` и тихих фолбэков** (правило 8). Ошибка → JobError/явный лог.
6. **Не коммить.** Прогоняй ТОЛЬКО свои таргетные тесты для верификации:
   ```powershell
   $env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
   Set-Location "C:\Users\user\Desktop\ClipClow\services\worker"
   uv run python -m pytest tests/unit/<твой_тест>.py -q
   ```
   Фронт: `Set-Location C:\Users\user\Desktop\ClipClow; pnpm --filter web exec tsc --noEmit` и `pnpm --filter web lint`.
7. **Отчёт обязателен.** Заполни `docs/night-audit/<domain>.md` по шаблону (см. низ файла).
8. Если DoD не сходится 2 раза подряд — СТОП, опиши проблему в отчёт, не угадывай.

## Матрица доменов (ownership)

### Backend (services/worker/app)
| ID | Роль | Ownership (файлы) | Тесты |
|----|------|-------------------|-------|
| BE-A | Import/Transcribe | `pipeline/stage0_import.py`, `pipeline/stage1_transcribe.py`, `transcript_cache.py`, `config.py`, `errors.py` | test_stage0_import, test_stage1_transcribe, test_stage1_contract, test_transcript_cache |
| BE-B | Select/Chapters (Gemini) | `pipeline/stage2_select.py`, `editor/chapters.py`, `prompts/**` | test_stage2_select, test_chapters, test_chapters_api |
| BE-C | Reframe ⚠️INVARIANT | `pipeline/stage3_reframe.py`, `pipeline/stage3_speaker.py`, `pipeline/asd_reframe.py`, `asd/**`, `editor/reframe_cache.py` | test_stage3_reframe, test_stage3_speaker, test_reframe_resolve |
| BE-D | Captions/Render | `pipeline/stage4_captions.py`, `pipeline/stage5_render.py`, `editor/captions_v2.py` | test_stage4_captions, test_stage5_render, test_captions_v2, test_emphasis, test_hook, test_timeline_filter, test_srt_export |
| BE-E | Editor backend | `editor/store.py`, `editor/ops.py`, `editor/timemap.py`, `editor/timeline.py`, `editor/replies.py`, `editor/defaults.py`, `editor/presets.py`, `editor/preset_seeds.py` | test_editor_store, test_editor_ops, test_timemap, test_replies, test_defaults, test_presets, test_set_interval, test_timeline_api, test_editor_api, test_editor_models |
| BE-F | Billing/Persistence/Auth | `billing.py`, `polar.py`, `db.py`, `supa.py`, `cloud_state.py`, `storage.py`, `auth.py`, `artifacts.py`, `dispatch.py` | test_billing, test_polar, test_db, test_supa, test_cloud_state, test_storage, test_auth |
| BE-G | API/Orchestration | `main.py`, `tasks.py`, `run.py`, `eval.py` | test_upload_api, test_models, test_models_contracts, test_eval |

### Frontend (apps/web)
| ID | Роль | Ownership (файлы) |
|----|------|-------------------|
| FE-A | Marketing/Landing/SEO | `app/(marketing)/page.tsx`, `app/(marketing)/layout.tsx`, `app/(marketing)/terms`, `app/(marketing)/privacy`, `components/marketing/**` (кроме Pricing*), `app/opengraph-image.tsx`, `app/robots.ts`, `app/sitemap.ts`, `lib/site.ts`, `lib/faq.ts`, `lib/jsonld.ts`, `app/layout.tsx` |
| FE-B | Auth + App shell + Dashboard | `app/(auth)/**`, `app/auth/callback/route.ts`, `app/(app)/layout.tsx`, `app/(app)/dashboard/page.tsx`, `lib/supabase/**`, `components/auth/**`, `components/app/**`, `lib/recent.ts` |
| FE-C | Editor | `app/(app)/edit/**`, `components/editor/**`, `components/LibassLayer.tsx`, `components/CaptionOverlay.tsx`, `components/PresetStrip.tsx`, `components/ClipPreview.tsx`, `components/ExportMenu.tsx` |
| FE-D | Core tool flow + API client | `components/SourceForm.tsx`, `components/JobProgress.tsx`, `components/ClipGrid.tsx`, `components/ClipCard.tsx`, `components/StatusBadge.tsx`, `components/ErrorPanel.tsx`, `components/ReasonChip.tsx`, `lib/api.ts`, `lib/useJob.ts`, `lib/format.ts`, `lib/cn.ts`, `lib/types.ts`, `app/api/mock/**` |
| FE-E | Pricing/Checkout | `app/(marketing)/pricing/page.tsx`, `components/marketing/Pricing.tsx`, `components/marketing/PricingCards.tsx`, `components/marketing/Comparison.tsx`, `components/marketing/CheckoutNotice.tsx`, `components/ui/CheckoutCta.tsx`, `lib/plans.ts`, `lib/polar.ts`, `app/checkout/route.ts` |

## Статус-доска (ФИНАЛ — все волны зелёные, закоммичены)
| Домен | Найдено | Починено | Главное | Коммит |
|-------|---------|----------|---------|--------|
| BE-A | 5 | 4 | parse_fps fps≤0 → ZeroDivisionError на рендере | 8a819f2 |
| BE-B | 3 | 1 | Gemini-ретрай fail-fast на неретраябельных (был ~2мин) | 8a819f2 |
| BE-C | 1 | 1 | detect_scene_cuts release в finally (Win file-lock) | 191816e |
| BE-D | 1 | 1 | escape_ass_text: {laughs} больше не пропадает | 191816e |
| BE-E | 5 | 4 | apply_trim 500→JobError; edge-валидация; overlap | 8a819f2 |
| BE-F | 6 | 2(+1крит) | Supabase upsert (оплата не терялась); крит PAYG→BE-H | 8a819f2 |
| BE-G | 5 | 5 | JobError→400; пустые главы→failed; spawn-сбой→failed | 191816e |
| BE-H | 1крит | 1 | **PAYG списание + двойной учёт устранён** | a6c8927 |
| BE-I | 5 | 1 | Modal cookies env/file mismatch (краш деплоя) | 9a07bf4 |
| FE-A | 3 | 1 | sitemap noindex/pricing; (+faq via orch.) | ecfb791 |
| FE-B | 3 | 3 | callback тихий сбой → петля редиректа; SignOut залип | ecfb791 |
| FE-C | 3 | 2(+1) | editRef → ложный 409→reload редактора | ecfb791 |
| FE-D | 3 | 3 | getJob таймаут (был бесконечный спиннер); часы/NaN | ecfb791 |
| FE-E | 1 | 1 | plans.ts↔billing.py дрейф=0; faq money-copy фикс | ecfb791 |
| FE-F | 3 | 2 | proxy.ts терял session-cookies → петля редиректа | 9a07bf4 |
| REVIEW | — | — | ✅ все 7 фокус-зон корректны, регрессий нет | — |

**Итого: ~48 багов найдено, ~32 починено, остальное — задокументировано фаундеру (см. `docs/NIGHT_AUDIT_REPORT_2026-06-15.md`).**

## Шаблон отчёта `docs/night-audit/<domain>.md`
```
# <DOMAIN> — отчёт агента
## Сводка
- Файлов проверено: N
- Багов найдено: N (crit X / high Y / med Z / low W)
- Багов починено: N
- Тесты добавлены: N, прогон: <команда + результат>

## Баги
### [SEV] Краткое имя — file:line
**Симптом:** ...
**Корень:** ...
**Фикс:** ... (или «не чинил, причина»)
**Тест:** ...

## Передать оркестратору (чужие/общие файлы)
- ...

## Не успел / открыто
- ...
```
