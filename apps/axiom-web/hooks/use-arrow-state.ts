"use client";

import { reactive, watch } from "@arrow-js/core";
import { useCallback, useEffect, useRef, useState } from "react";

type ArrowStateSetter<T> = T | ((previousValue: T) => T);

/**
 * Arrow-backed state with a React-compatible API.
 *
 * The source of truth lives in Arrow's reactive store, while React subscribes
 * through `watch()` to re-render on updates.
 */
export function useArrowState<T>(initialValue: T): [T, (nextValue: ArrowStateSetter<T>) => void] {
  const storeRef = useRef<ReturnType<typeof reactive<{ value: T }>> | null>(null);
  if (!storeRef.current) {
    storeRef.current = reactive({ value: initialValue });
  }

  const store = storeRef.current as unknown as { value: T };
  const [value, setValue] = useState<T>(store.value);

  useEffect(() => {
    const [, stop] = watch(
      () => store.value,
      (nextValue) => {
        setValue(nextValue as T);
        return nextValue;
      },
    );

    return stop;
  }, [store]);

  const setArrowValue = useCallback(
    (nextValue: ArrowStateSetter<T>) => {
      const currentValue = store.value;
      store.value =
        typeof nextValue === "function"
          ? (nextValue as (previousValue: T) => T)(currentValue)
          : nextValue;
    },
    [store],
  );

  return [value, setArrowValue];
}
