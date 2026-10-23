import { useCallback, useEffect, useRef, useState } from 'react';
import { api, errorMessage } from '../api/client';

/** GET helper with loading/error state, manual reload and optional polling. */
export function useFetch(url, { params, interval, enabled = true } = {}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(Boolean(url) && enabled);
  const alive = useRef(true);
  const hasData = useRef(false);
  const key = JSON.stringify(params || {});

  // `loading` is only true until the first response for this url/params. Later reloads keep the
  // current data on screen so child components (and their local state) are not unmounted.
  const load = useCallback(async (silent = false) => {
    if (!url || !enabled) return;
    if (!silent && !hasData.current) setLoading(true);
    try {
      const r = await api.get(url, { params: params || undefined });
      if (alive.current) { setData(r.data); setError(null); hasData.current = true; }
    } catch (e) {
      if (alive.current) setError(errorMessage(e));
    } finally {
      if (alive.current && !silent) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, key, enabled]);

  useEffect(() => { alive.current = true; hasData.current = false; load(); return () => { alive.current = false; }; }, [load]);
  useEffect(() => {
    if (!interval || !enabled) return undefined;
    const t = setInterval(() => load(true), interval);
    return () => clearInterval(t);
  }, [interval, load, enabled]);

  return { data, error, loading, reload: load, setData };
}

export const results = (d) => (Array.isArray(d) ? d : d?.results || []);
