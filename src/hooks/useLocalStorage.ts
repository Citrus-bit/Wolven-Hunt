import { useCallback, useEffect, useRef, useState } from 'react';

export type LocalStorageSerializer<T> = {
  read: (raw: string) => T;
  write: (value: T) => string;
};

export function useLocalStorage<T>(
  key: string,
  initialValue: T,
  serializer: LocalStorageSerializer<T>,
  options?: { debounceMs?: number },
): [T, (next: T) => void] {
  const debounceMs = options?.debounceMs ?? 0;
  const timer = useRef<number | null>(null);
  const pendingValue = useRef<T | null>(null);

  const [value, setValue] = useState<T>(() => {
    if (typeof window === 'undefined') {
      return initialValue;
    }

    try {
      const raw = window.localStorage.getItem(key);
      return raw === null ? initialValue : serializer.read(raw);
    } catch (error) {
      console.warn(`[lobby] failed to read localStorage key=${key}`, error);
      return initialValue;
    }
  });

  const writeNow = useCallback(
    (next: T) => {
      if (typeof window === 'undefined') {
        return;
      }

      try {
        window.localStorage.setItem(key, serializer.write(next));
      } catch (error) {
        console.warn(`[lobby] failed to write localStorage key=${key}`, error);
      }
    },
    [key, serializer],
  );

  const update = useCallback(
    (next: T) => {
      setValue(next);

      if (debounceMs <= 0) {
        pendingValue.current = null;
        writeNow(next);
        return;
      }

      pendingValue.current = next;

      if (timer.current !== null) {
        window.clearTimeout(timer.current);
      }

      timer.current = window.setTimeout(() => {
        timer.current = null;
        if (pendingValue.current !== null) {
          writeNow(pendingValue.current);
          pendingValue.current = null;
        }
      }, debounceMs);
    },
    [debounceMs, writeNow],
  );

  useEffect(
    () => () => {
      if (timer.current !== null) {
        window.clearTimeout(timer.current);
      }

      if (pendingValue.current !== null) {
        writeNow(pendingValue.current);
      }
    },
    [writeNow],
  );

  return [value, update];
}
