import { useEffect, useRef } from "react";

// ────────────────────────────────────────────────────────────────────────────
// useWheelHscroll — превратить ВЕРТИКАЛЬНОЕ колесо мыши / тачпада в ГОРИЗОНТАЛЬНЫЙ
// скролл контейнера. У ноутбучных тачпадов/мышей нет горизонтального колеса, поэтому
// ленты пресетов (`overflow-x-auto`) на ноуте не листались (фидбек фаундера #6).
//
// Слушатель вешаем ИМПЕРАТИВНО (addEventListener) с `{ passive: false }`: React
// onWheel пассивен → там `preventDefault()` молча игнорируется и страница скроллит
// вместо ленты. Перехватываем ТОЛЬКО когда: (1) контейнер реально переполнен по
// горизонтали и (2) жест преимущественно вертикальный (настоящий горизонтальный
// свайп тачпада уже листает нативно — его не трогаем). Возвращаем ref на контейнер.
// ────────────────────────────────────────────────────────────────────────────
export function useWheelHscroll<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (el.scrollWidth <= el.clientWidth) return; // нечего листать
      if (Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return; // уже горизонтальный жест
      el.scrollLeft += e.deltaY;
      e.preventDefault(); // не отдаём жест вертикальному скроллу страницы
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);
  return ref;
}
