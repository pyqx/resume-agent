"use client";

import { createContext, useContext, useCallback, useState, type ReactNode } from "react";

interface PageState {
  [key: string]: unknown;
}

interface PageStateContextValue {
  getState: <T>(page: string) => Partial<T> | undefined;
  setState: <T>(page: string, data: Partial<T>) => void;
}

const PageStateContext = createContext<PageStateContextValue | null>(null);

export function PageStateProvider({ children }: { children: ReactNode }) {
  const [store, setStore] = useState<Record<string, PageState>>({});

  const getState = useCallback(<T,>(page: string): Partial<T> | undefined => {
    return store[page] as Partial<T> | undefined;
  }, [store]);

  const setState = useCallback(<T,>(page: string, data: Partial<T>) => {
    setStore((prev) => ({
      ...prev,
      [page]: { ...(prev[page] || {}), ...data },
    }));
  }, []);

  return (
    <PageStateContext.Provider value={{ getState, setState }}>
      {children}
    </PageStateContext.Provider>
  );
}

export function usePageState<T>(page: string): {
  state: Partial<T>;
  updateState: (data: Partial<T>) => void;
  clearState: () => void;
} {
  const ctx = useContext(PageStateContext);
  if (!ctx) throw new Error("usePageState must be used within PageStateProvider");

  const state = (ctx.getState<T>(page) || {}) as Partial<T>;

  const updateState = useCallback(
    (data: Partial<T>) => ctx.setState<T>(page, data),
    [ctx, page],
  );

  const clearState = useCallback(() => {
    ctx.setState(page, {} as Partial<T>);
  }, [ctx, page]);

  return { state, updateState, clearState };
}
