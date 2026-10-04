'use client';
import { useSyncExternalStore, type Dispatch, type SetStateAction } from 'react';

type Value = string | number | boolean;
type HistoryMode = 'push' | 'replace';
const changeEvent = 'radar:urlchange';
export const viewNames: Record<string, string> = {
  feed: '信息流', saved: '收藏', sources: '来源管理', import: '录入资料', topics: '主题设置', semantic: '语义去重',
};
export const viewKey = (name: string) =>
  Object.keys(viewNames).find((key) => viewNames[key] === name) || 'feed';

function subscribe(callback: () => void) {
  window.addEventListener('popstate', callback);
  window.addEventListener(changeEvent, callback);
  return () => {
    window.removeEventListener('popstate', callback);
    window.removeEventListener(changeEvent, callback);
  };
}
const snapshot = () => window.location.search;
const serverSnapshot = () => '';

export function updateUrlState(updates: Record<string, Value | null>, mode: HistoryMode = 'replace') {
  const url = new URL(window.location.href);
  for (const [key, value] of Object.entries(updates)) {
    if (value === null) url.searchParams.delete(key);
    else url.searchParams.set(key, typeof value === 'boolean' ? (value ? '1' : '0') : String(value));
  }
  if (url.href === window.location.href) return;
  if (mode === 'push') window.history.pushState(null, '', url);
  else window.history.replaceState(null, '', url);
  window.dispatchEvent(new Event(changeEvent));
}

type Options<T> = { history?: HistoryMode; values?: readonly T[] };
type StoredValue<T> = T extends string ? string : T extends number ? number : boolean;
export function useUrlState<T extends Value>(
  key: string,
  fallback: T,
  options: Options<StoredValue<T>> = {},
): [StoredValue<T>, Dispatch<SetStateAction<StoredValue<T>>>] {
  const search = useSyncExternalStore(subscribe, snapshot, serverSnapshot);
  function read(raw: string | null): Value {
    if (raw === null) return fallback;
    let value: Value = raw;
    if (typeof fallback === 'number') {
      const number = /^\d{1,7}$/.test(raw) ? Number(raw) : NaN;
      value = Number.isSafeInteger(number) ? number : fallback;
    } else if (typeof fallback === 'boolean') value = raw === '1';
    if (options.values && !options.values.includes(value as StoredValue<T>)) return fallback;
    return value;
  }
  const value = read(new URLSearchParams(search).get(key));
  const set: Dispatch<SetStateAction<Value>> = (next) => {
    const current = read(new URLSearchParams(window.location.search).get(key));
    const result = typeof next === 'function' ? next(current) : next;
    updateUrlState({ [key]: result === fallback ? null : result }, options.history);
  };
  return [value as StoredValue<T>, set as Dispatch<SetStateAction<StoredValue<T>>>];
}
