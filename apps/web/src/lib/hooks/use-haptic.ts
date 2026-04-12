'use client';

import { useMemo } from 'react';

type Pattern = number | number[];

function vibrate(pattern: Pattern): void {
  if (typeof navigator === 'undefined') return;
  if (typeof navigator.vibrate !== 'function') return;
  try {
    navigator.vibrate(pattern);
  } catch {
    /* ignore */
  }
}

export function useHaptic() {
  return useMemo(
    () => ({
      light: () => vibrate(10),
      medium: () => vibrate(20),
      heavy: () => vibrate(40),
      success: () => vibrate([10, 30, 10]),
      warning: () => vibrate([20, 40, 20]),
      error: () => vibrate([50, 100, 50]),
    }),
    [],
  );
}
