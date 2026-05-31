"use client";

import { useState, useCallback } from "react";
import { uploadResume, getResume, listResumes } from "@/lib/api";

interface ResumeState {
  resumeId: string | null;
  resumeData: Record<string, unknown> | null;
  isLoading: boolean;
  error: string | null;
}

export function useResume() {
  const [state, setState] = useState<ResumeState>({
    resumeId: null,
    resumeData: null,
    isLoading: false,
    error: null,
  });

  const upload = useCallback(async (file: File) => {
    setState((s) => ({ ...s, isLoading: true, error: null }));
    try {
      const result = await uploadResume(file);
      setState({
        resumeId: result.resume_id,
        resumeData: result.resume,
        isLoading: false,
        error: null,
      });
      return result;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Upload failed";
      setState((s) => ({ ...s, isLoading: false, error: msg }));
      throw err;
    }
  }, []);

  const load = useCallback(async (resumeId: string) => {
    setState((s) => ({ ...s, isLoading: true, error: null }));
    try {
      const data = await getResume(resumeId);
      setState({
        resumeId,
        resumeData: data,
        isLoading: false,
        error: null,
      });
      return data;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Load failed";
      setState((s) => ({ ...s, isLoading: false, error: msg }));
      throw err;
    }
  }, []);

  const clear = useCallback(() => {
    setState({
      resumeId: null,
      resumeData: null,
      isLoading: false,
      error: null,
    });
  }, []);

  return {
    ...state,
    upload,
    load,
    clear,
  };
}
