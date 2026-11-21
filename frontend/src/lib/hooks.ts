"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, responseCache } from "./api";

const CACHE_MS = 5 * 60_000;
const cached = <T,>(path: string | null): T | null => {
  if (!path) return null;
  const hit = responseCache.get(path);
  return hit && Date.now() - hit.at < CACHE_MS ? (hit.data as T) : null;
};

/** Fetch JSON from the API; optionally re-poll every `refreshMs` (live data). */
export function useApi<T>(path: string | null, refreshMs?: number, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(() => cached<T>(path));
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState<boolean>(!!path && !cached(path));
  const alive = useRef(true);

  const load = useCallback(async () => {
    if (!path) return;
    try {
      const d = await api<T>(path);
      responseCache.set(path, { at: Date.now(), data: d });
      if (responseCache.size > 300) responseCache.delete(responseCache.keys().next().value as string);
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
    const hit = cached<T>(path);
    if (hit) setData(hit);
    setLoading(!!path && !hit);
    load();
    if (!refreshMs || !path) return () => { alive.current = false; };
    const id = setInterval(load, refreshMs);
    return () => { alive.current = false; clearInterval(id); };
  }, [load, refreshMs, path]);

  return { data, error, loading, reload: load, setData };
}
