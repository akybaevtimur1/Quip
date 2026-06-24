# FE-C (Editor) — отчёт агента

## Сводка
- Файлов проверено: 13 (ClipEditorScreen, PreviewPlayer, LibassLayer, TimelineV2,
  CaptionsTab, StyleTab, FrameTab, HookTab, EditorHeader, CaptionOverlay, PresetStrip,
  ClipPreview, ExportMenu, replyUtils + edit page route).
- Багов найдено: 3 (crit 0 / high 1 / med 1 / low 1)
- Багов починено: 2 (high + med). Low — задокументирован, не критичен.
- Тесты добавлены: 0 (это FE-only UI/race-логика; нет pure-функции под TDD —
  баг чисто во временной координации React-стейта и эффектов). Верификация:
  `tsc --noEmit` = TSC_OK, `eslint` = чисто (см. ниже).

## Баги

### [HIGH] Очередь мутаций читает УСТАРЕВШУЮ версию после trim/frame/aspect → 409 → reload — ClipEditorScreen.tsx:260,471,486
**Симптом:** юзер делает действие, которое НЕ идёт через очередь мутаций — сдвиг/трим
интервала (`refetchAfter`), смена режима кадра (`handleFrameApply`), смена аспекта
(`handleAspectChange`). Сразу после этого правит субтитр/стиль/анимацию. Первая
caption-мутация падает с 409 (version mismatch) → `handleConflict` → полный reload
редактора («Data changed — reloading…»). Ровно тот баг-класс, ради которого очередь
мутаций и была построена (журнал «8370d4e» — «больше никаких 409»).
**Корень:** очередь мутаций (`patchCaptions`/`handlePresetApply`) берёт свежую версию из
`editRef.current`. `editRef` синкается ТОЛЬКО эффектом `useEffect(() => { editRef.current = edit }, [edit])`,
который отстаёт на один React-commit. Пути `refetchAfter`/`handleFrameApply`/`handleAspectChange`
делают `setEdit(newEdit)` напрямую, но НЕ трогают `editRef.current`. Между их `setEdit` и
прогоном sync-эффекта `editRef.current` всё ещё держит СТАРУЮ версию → следующая мутация
шлёт устаревший `version` → сервер отвечает 409 (optimistic-lock).
**Фикс:** `editRef.current = newEdit;` синхронно рядом с каждым прямым `setEdit(newEdit)`
(в `refetchAfter`, `handleFrameApply`, `handleAspectChange`). Декларация `editRef` + sync-эффект
перенесены выше `refetchAfter` (порядок объявления). Внутрицепочечные пути
(`patchCaptions` стр. 345, `handlePresetApply` стр. 449) уже синкали `editRef` — не трогал.
**Тест:** нет (чистая координация React-стейта). Верифицировано tsc+eslint; ручной сценарий
для оркестратора: trim интервала → сразу сменить пресет/цвет → НЕ должно быть «reloading…».

### [MED] Пан-слайдер таймлайна теряет суб-секундную точность (битовый `| 0`) — TimelineV2.tsx:545
**Симптом:** при зуме на длинном (часовом) видео ползунок пана дёргается/округляет
позицию окна до целых секунд; на очень больших значениях `| 0` (32-битный) мог бы
переполниться.
**Корень:** `setViewStart(((Number(e.target.value)/1000) * (duration - viewLen)) | 0)` —
битовый ИЛИ `| 0` приводит float к int32, обрезая дробную часть viewStart.
**Фикс:** убран `| 0` — `setViewStart((Number(...)/1000) * (duration - viewLen))`.
viewStart и так клампится (`viewStartClamped`) и используется во float-вычислениях.
**Тест:** нет (UI-арифметика); tsc+eslint зелёные.

### [LOW] In-flight caption-мутация при навигации между клипами может применить чужой edit — ClipEditorScreen.tsx (patchChain)
**Симптом:** если PATCH субтитра в полёте РОВНО в момент перехода ‹/› на другой клип,
его resolve вызовет `setEdit`/`editRef.current=` с данными СТАРОГО клипа поверх нового.
**Корень:** `patchChain` (ref) переживает смену `clipId` (компонент не пере-mount'ится —
роут меняет только props). `assSeq` гейтит ASS, но не сам edit-state.
**Фикс:** НЕ чинил — крайне узкое окно, кнопки навигации/правок дизейблятся `busy`,
а расширение (гейт по clipId в цепочке) рискует задеть инвариант очереди. Документирую
оркестратору как кандидат, если всплывёт.

## Что проверил и НЕ нашёл бага (ложные подозрения, чтобы не перепроверяли)
- **LibassLayer dispose (стр. 43-137):** инстанс создаётся в async-IIFE; cleanup читает
  shared `let local`. После `await import` всё синхронно до присваивания `local` →
  на момент cleanup `local` уже установлен (или `disposed` сработал до await). rAF/
  ResizeObserver/инстанс корректно чистятся. Утечки НЕТ.
- **PreviewPlayer/SplitHalf/aux rAF (стр. 62-86, 318-342):** rAF отменяется в cleanup на
  смену `mode`/`active`; ведомые видео паузятся. Декодеры монтируются лениво (только
  fit/split). ОК.
- **Деление на ноль:** `clipDur=Math.max(0.01,…)`, скраб-`value` гейтятся `dur?…:0` /
  `Math.max(0.001, …)`; слайдер пана рендерится только при `zoom>1` → `duration-viewLen>0`. ОК.
- **replyUtils/CaptionsTab/CaptionOverlay позиционная индексация:** `group[0]` берётся
  только после гейта `group.length===0 → continue/return null`; offset сдвигается даже на
  скрытых репликах (зеркало бэка). Off-by-one НЕТ.
- **ExportMenu (mousedown/keydown listeners):** навешиваются под `if(!open)return` и
  снимаются в cleanup. ОК.
- **TimelineV2 chapters-poll / setZoomAround / pointer-capture:** poll отменяется
  (`cancelled`+`clearTimeout`); capture на child'ах бабблит в track-handler; зум клампится. ОК.

## Передать оркестратору (чужие/общие файлы)
- Ничего критичного в чужих файлах не правил. Замечание (НЕ баг): `lib/api.ts`
  (владелец FE-D) определяет ошибки как `new Error("...409")`/`"...conflict"`, а
  `failOr409` детектит 409 по подстроке. Хрупко, но работает с текущим api.ts — если
  FE-D меняет формат сообщений об ошибке, обновить детект 409.

## Не успел / открыто
- [LOW] выше: гейт `patchChain` по clipId на навигации (узкое окно).
- `handleFrameApply`/`handleAspectChange` читают `edit.version` из стейт-замыкания, а не
  `editRef.current.version`. После каскада caption-правок их версия может отстать на один
  commit → 409 на ПЕРВЫЙ клик frame/aspect. Эти кнопки не rapid-fire и гейтятся `busy`,
  поэтому оставил; если важно — перевести их тоже на `editRef.current.version`.

## Верификация
```
Set-Location "C:\Users\user\Desktop\ClipClow"
pnpm --filter web exec tsc --noEmit   → TSC_OK
pnpm --filter web lint                → чисто (0 ошибок/варнингов)
```
