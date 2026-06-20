export interface ClipCache<T> {
  get(id: string): T | undefined;
  set(id: string, v: T): void;
  has(id: string): boolean;
  size(): number;
}

export function createClipCache<T>(max: number): ClipCache<T> {
  const m = new Map<string, T>(); // Map preserves insertion order → front = oldest
  return {
    get: (id) => m.get(id),
    has: (id) => m.has(id),
    size: () => m.size,
    set(id, v) {
      if (m.has(id)) m.delete(id);     // refresh recency
      m.set(id, v);
      while (m.size > max) m.delete(m.keys().next().value as string);
    },
  };
}
