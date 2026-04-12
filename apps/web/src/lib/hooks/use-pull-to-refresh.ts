'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

interface UsePullToRefreshOptions {
  onRefresh: () => Promise<void> | void;
  threshold?: number;
  resistance?: number;
}

interface UsePullToRefreshResult {
  bind: {
    ref: (node: HTMLElement | null) => void;
  };
  isPulling: boolean;
  pullDistance: number;
  isRefreshing: boolean;
}

export function usePullToRefresh({
  onRefresh,
  threshold = 70,
  resistance = 2.5,
}: UsePullToRefreshOptions): UsePullToRefreshResult {
  const [isPulling, setIsPulling] = useState(false);
  const [pullDistance, setPullDistance] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const nodeRef = useRef<HTMLElement | null>(null);
  const startYRef = useRef<number | null>(null);
  const currentDistanceRef = useRef(0);

  const finish = useCallback(async () => {
    const dist = currentDistanceRef.current;
    setIsPulling(false);
    if (dist >= threshold) {
      setIsRefreshing(true);
      try {
        await onRefresh();
      } finally {
        setIsRefreshing(false);
      }
    }
    setPullDistance(0);
    currentDistanceRef.current = 0;
    startYRef.current = null;
  }, [onRefresh, threshold]);

  useEffect(() => {
    const node = nodeRef.current;
    if (!node) return;

    const onTouchStart = (e: TouchEvent) => {
      if (node.scrollTop > 0) return;
      startYRef.current = e.touches[0].clientY;
    };

    const onTouchMove = (e: TouchEvent) => {
      if (startYRef.current === null) return;
      const delta = e.touches[0].clientY - startYRef.current;
      if (delta <= 0) {
        currentDistanceRef.current = 0;
        setPullDistance(0);
        setIsPulling(false);
        return;
      }
      const eased = delta / resistance;
      currentDistanceRef.current = eased;
      setPullDistance(eased);
      setIsPulling(true);
    };

    const onTouchEnd = () => {
      if (startYRef.current === null) return;
      finish();
    };

    node.addEventListener('touchstart', onTouchStart, { passive: true });
    node.addEventListener('touchmove', onTouchMove, { passive: true });
    node.addEventListener('touchend', onTouchEnd);
    node.addEventListener('touchcancel', onTouchEnd);
    return () => {
      node.removeEventListener('touchstart', onTouchStart);
      node.removeEventListener('touchmove', onTouchMove);
      node.removeEventListener('touchend', onTouchEnd);
      node.removeEventListener('touchcancel', onTouchEnd);
    };
  }, [finish, resistance]);

  const setRef = useCallback((node: HTMLElement | null) => {
    nodeRef.current = node;
  }, []);

  return {
    bind: { ref: setRef },
    isPulling,
    pullDistance,
    isRefreshing,
  };
}
