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
  const [value, setValue] = useState<T>(initialValue);
  const initialValueRef = useRef(initialValue);
  const storeRef = useRef<{ value: T } | null>(null);

  useEffect(() => {
    const store = reactive({ value: initialValueRef.current }) as unknown as { value: T };
    storeRef.current = store;

    const [, stop] = watch(
      () => store.value,
      (nextValue) => {
        setValue(nextValue as T);
        return nextValue;
      },
    );

    return () => {
      stop();
      storeRef.current = null;
    };
  }, []);

  const setArrowValue = useCallback(
    (nextValue: ArrowStateSetter<T>) => {
      const store = storeRef.current;
      if (!store) {
        setValue((previousValue) =>
          typeof nextValue === "function"
            ? (nextValue as (currentValue: T) => T)(previousValue)
            : nextValue,
        );
        return;
      }

      const currentValue = store.value;
      store.value =
        typeof nextValue === "function"
          ? (nextValue as (previousValue: T) => T)(currentValue)
          : nextValue;
    },
    [],
  );

  return [value, setArrowValue];
}
