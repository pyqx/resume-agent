"use client";

import {
  createContext,
  useContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

type PageState = Record<string, unknown>;
type Store = Record<string, PageState>;

const STORAGE_KEY = "resume-agent:page-state";
const EMPTY_STATE: PageState = {};

interface PageStateContextValue {
  store: Store;
  /** True once sessionStorage has been read back on the client. */
  hydrated: boolean;
  setPageState: (page: string, data: PageState) => void;
  clearPageState: (page: string) => void;
}

const PageStateContext = createContext<PageStateContextValue | null>(null);

export function PageStateProvider({ children }: { children: ReactNode }) {
  const [store, setStore] = useState<Store>({});
  const [hydrated, setHydrated] = useState(false);

  // Restore from sessionStorage after mount (not in the initializer, which
  // would make the client's first render differ from SSR and break
  // hydration). Anything written between mount and this effect wins.
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (raw) {
        const persisted = JSON.parse(raw) as Store;
        if (persisted && typeof persisted === "object") {
          setStore((prev) => {
            const merged: Store = { ...persisted };
            for (const page of Object.keys(prev)) {
              merged[page] = { ...(persisted[page] ?? {}), ...prev[page] };
            }
            return merged;
          });
        }
      }
    } catch {
      // Corrupt or unavailable storage — start fresh.
    }
    setHydrated(true);
  }, []);

  // Page state holds expensive LLM output (match reports, interview
  // questions, chat turns) — persist it so a refresh doesn't wipe it.
  useEffect(() => {
    if (!hydrated) return;
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(store));
    } catch {
      // Quota exceeded / unavailable — persistence is best-effort.
    }
  }, [store, hydrated]);

  const setPageState = useCallback((page: string, data: PageState) => {
    setStore((prev) => ({
      ...prev,
      [page]: { ...(prev[page] ?? {}), ...data },
    }));
  }, []);

  // Really delete the page's entry — merging in an empty object (the old
  // implementation) cleared nothing.
  const clearPageState = useCallback((page: string) => {
    setStore((prev) => {
      if (!(page in prev)) return prev;
      const next = { ...prev };
      delete next[page];
      return next;
    });
  }, []);

  const value = useMemo<PageStateContextValue>(
    () => ({ store, hydrated, setPageState, clearPageState }),
    [store, hydrated, setPageState, clearPageState],
  );

  return (
    <PageStateContext.Provider value={value}>
      {children}
    </PageStateContext.Provider>
  );
}

export function usePageState<T>(page: string): {
  state: Partial<T>;
  updateState: (data: Partial<T>) => void;
  clearState: () => void;
  /** True once persisted state has been restored on the client. */
  hydrated: boolean;
} {
  const ctx = useContext(PageStateContext);
  if (!ctx) throw new Error("usePageState must be used within PageStateProvider");

  const { store, hydrated, setPageState, clearPageState } = ctx;
  const state = (store[page] ?? EMPTY_STATE) as Partial<T>;

  const updateState = useCallback(
    (data: Partial<T>) => setPageState(page, data as PageState),
    [setPageState, page],
  );

  const clearState = useCallback(() => clearPageState(page), [clearPageState, page]);

  return { state, updateState, clearState, hydrated };
}
