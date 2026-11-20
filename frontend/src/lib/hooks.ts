"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";

/** Fetch JSON from the API; optionally re-poll every `refreshMs` (live data). */
export function useApi<T>(path: string | null, refreshMs?: number, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState<boolean>(!!path);
  const alive = useRef(true);

  const load = useCallback(async () => {
    if (!path) return;
    try {
      const d = await api<T>(path);
      if (alive.current) { setData(d); setError(null); }
    } catch (e) {
      if (alive.current) setError(e instanceof ApiError ? e : new ApiError(0, String(e)));
    } finally {
      if (alive.current) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps]);

  useEffect(() => {
    alive.current = true;
    setLoading(!!path);
    load();
    if (!refreshMs || !path) return () => { alive.current = false; };
    const id = setInterval(load, refreshMs);
    return () => { alive.current = false; clearInterval(id); };
  }, [load, refreshMs, path]);

  return { data, error, loading, reload: load, setData };
}
