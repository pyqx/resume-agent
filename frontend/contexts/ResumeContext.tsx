"use client";

import {
  createContext,
  useContext,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ApiError, getErrorMessage, resumeApi } from "@/lib/api";
import type { Resume, UploadResult } from "@/lib/types";

const STORAGE_KEY = "resume-agent:resume-id";

interface ResumeContextValue {
  resumeId: string | null;
  resumeData: Resume | null;
  isLoading: boolean;
  error: string | null;
  upload: (file: File) => Promise<UploadResult>;
  load: (resumeId: string) => Promise<Resume>;
  clear: () => void;
  refresh: () => Promise<void>;
  updateEntry: (entryId: string, updates: Record<string, unknown>) => Promise<void>;
  deleteEntry: (entryId: string) => Promise<void>;
  clearError: () => void;
}

const ResumeContext = createContext<ResumeContextValue | null>(null);

function persistId(id: string | null) {
  try {
    if (id) localStorage.setItem(STORAGE_KEY, id);
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    // localStorage unavailable (private mode) — persistence is best-effort
  }
}

export function ResumeProvider({ children }: { children: ReactNode }) {
  const [resumeId, setResumeId] = useState<string | null>(null);
  const [resumeData, setResumeData] = useState<Resume | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Concurrency guard: every state-mutating request takes a sequence number;
  // a response is applied only if no newer request has started since.
  const seqRef = useRef(0);
  // Mirror of resumeId for callbacks that must not re-create on every change.
  const resumeIdRef = useRef<string | null>(null);

  const load = useCallback(async (id: string): Promise<Resume> => {
    const seq = ++seqRef.current;
    setIsLoading(true);
    setError(null);
    try {
      const data = await resumeApi.get(id);
      if (seq === seqRef.current) {
        resumeIdRef.current = id;
        setResumeId(id);
        setResumeData(data);
        setIsLoading(false);
        persistId(id);
      }
      return data;
    } catch (err) {
      if (seq === seqRef.current) {
        setIsLoading(false);
        setError(getErrorMessage(err, "加载简历失败"));
      }
      throw err;
    }
  }, []);

  const upload = useCallback(async (file: File): Promise<UploadResult> => {
    const seq = ++seqRef.current;
    setIsLoading(true);
    setError(null);
    try {
      const result = await resumeApi.upload(file);
      if (seq === seqRef.current) {
        resumeIdRef.current = result.resume_id;
        setResumeId(result.resume_id);
        setResumeData(result.resume);
        setIsLoading(false);
        persistId(result.resume_id);
      }
      return result;
    } catch (err) {
      if (seq === seqRef.current) {
        setIsLoading(false);
        setError(getErrorMessage(err, "上传简历失败"));
      }
      throw err;
    }
  }, []);

  const clear = useCallback(() => {
    seqRef.current += 1; // invalidate any in-flight request
    resumeIdRef.current = null;
    setResumeId(null);
    setResumeData(null);
    setIsLoading(false);
    setError(null);
    persistId(null);
  }, []);

  /** Re-fetch the current resume silently (no loading flicker). */
  const refresh = useCallback(async (): Promise<void> => {
    const id = resumeIdRef.current;
    if (!id) return;
    const seq = ++seqRef.current;
    try {
      const data = await resumeApi.get(id);
      if (seq === seqRef.current && resumeIdRef.current === id) {
        setResumeData(data);
      }
    } catch (err) {
      if (seq === seqRef.current) {
        setError(getErrorMessage(err, "刷新简历失败"));
      }
    }
  }, []);

  const updateEntry = useCallback(
    async (entryId: string, updates: Record<string, unknown>): Promise<void> => {
      const id = resumeIdRef.current;
      if (!id) {
        const msg = "尚未加载简历,无法编辑条目";
        setError(msg);
        throw new ApiError(0, msg);
      }
      setError(null);
      try {
        await resumeApi.updateEntry(id, entryId, updates);
      } catch (err) {
        setError(getErrorMessage(err, "更新条目失败"));
        throw err;
      }
      await refresh();
    },
    [refresh],
  );

  const deleteEntry = useCallback(
    async (entryId: string): Promise<void> => {
      const id = resumeIdRef.current;
      if (!id) {
        const msg = "尚未加载简历,无法删除条目";
        setError(msg);
        throw new ApiError(0, msg);
      }
      setError(null);
      try {
        await resumeApi.deleteEntry(id, entryId);
      } catch (err) {
        setError(getErrorMessage(err, "删除条目失败"));
        throw err;
      }
      await refresh();
    },
    [refresh],
  );

  const clearError = useCallback(() => setError(null), []);

  // Boot restore: prefer the backend's current selection, then the id kept
  // in localStorage — but only if it still exists on the backend.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      let stored: string | null = null;
      try {
        stored = localStorage.getItem(STORAGE_KEY);
      } catch {
        stored = null;
      }
      try {
        const listing = await resumeApi.list();
        if (cancelled) return;
        const existing = new Set(listing.resumes.map((r) => r.id));
        const candidate =
          (listing.current_resume_id && existing.has(listing.current_resume_id)
            ? listing.current_resume_id
            : null) || (stored && existing.has(stored) ? stored : null);
        if (!candidate) {
          persistId(null); // drop a stale stored id
          return;
        }
        // Skip if the user already started an action (upload/load) meanwhile.
        if (seqRef.current === 0) {
          await load(candidate);
        }
      } catch (err) {
        // Backend unreachable at boot — the sidebar surfaces connectivity;
        // keep the workspace empty instead of blocking on an error.
        console.warn("简历自动恢复失败:", err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [load]);

  const value = useMemo<ResumeContextValue>(
    () => ({
      resumeId,
      resumeData,
      isLoading,
      error,
      upload,
      load,
      clear,
      refresh,
      updateEntry,
      deleteEntry,
      clearError,
    }),
    [
      resumeId,
      resumeData,
      isLoading,
      error,
      upload,
      load,
      clear,
      refresh,
      updateEntry,
      deleteEntry,
      clearError,
    ],
  );

  return <ResumeContext.Provider value={value}>{children}</ResumeContext.Provider>;
}

export function useResumeContext(): ResumeContextValue {
  const ctx = useContext(ResumeContext);
  if (!ctx) throw new Error("useResumeContext must be used within ResumeProvider");
  return ctx;
}
