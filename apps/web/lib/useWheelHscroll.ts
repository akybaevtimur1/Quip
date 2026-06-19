import { useCallback, useRef } from "react";

// ────────────────────────────────────────────────────────────────────────────
// useWheelHscroll — превратить ВЕРТИКАЛЬНОЕ колесо мыши / тачпада в ГОРИЗОНТАЛЬНЫЙ
// скролл контейнера. У ноутбучных тачпадов/мышей нет горизонтального колеса, поэтому
// ленты пресетов (`overflow-x-auto`) на ноуте не листались (фидбек фаундера #6).
//
// Возвращает CALLBACK-ref (а не useRef-объект + useEffect): слушатель вешается в момент,
// когда React монтирует РЕАЛЬНЫЙ узел. Это важно — лента пресетов сначала рендерит
// СКЕЛЕТОН (без ref), потом подменяет на реальный контейнер после загрузки `getPresets`.
// useEffect([]) отработал бы на маунте, когда ref ещё null (скелетон), и больше не
// перевесил бы listener → колесо не работало. Callback-ref срабатывает на реальном узле.
//
// Слушатель — `{ passive: false }`: React onWheel пассивен, там `preventDefault()` молча
// игнорируется и страница скроллит вместо ленты. Перехватываем ТОЛЬКО когда: (1) контейнер
// реально переполнен по горизонтали и (2) жест преимущественно вертикальный (настоящий
// горизонтальный свайп тачпада уже листает нативно — его не трогаем).
// ────────────────────────────────────────────────────────────────────────────
export function useWheelHscroll<T extends HTMLElement>() {
  const cleanupRef = useRef<(() => void) | null>(null);
  return useCallback((el: T | null) => {
    // отцепить прежний listener (узел сменился/размонтировался)
    if (cleanupRef.current) {
      cleanupRef.current();
      cleanupRef.current = null;
    }
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (el.scrollWidth <= el.clientWidth) return; // нечего листать
      if (Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return; // уже горизонтальный жест
      el.scrollLeft += e.deltaY;
      e.preventDefault(); // не отдаём жест вертикальному скроллу страницы
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    cleanupRef.current = () => el.removeEventListener("wheel", onWheel);
  }, []);
}
