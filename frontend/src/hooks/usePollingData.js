import { useEffect, useState, useCallback } from "react";

/**
 * Hook that polls a data source on an interval and returns
 * { data, loading, error, refetch }.
 * `fetcher(signal)` must be a function that accepts an AbortSignal.
 */
export const usePollingData = (fetcher, intervalMs = 15000, deps = []) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const refetch = useCallback(async (signal) => {
    signal = signal || (typeof AbortSignal !== "undefined" ? new AbortController().signal : null);
    setLoading(true);
    setError(null);
    try {
      const result = await fetcher(signal);
      setData(result);
      return result;
    } catch (err) {
      if (signal && signal.aborted) return;
      setError(err.message || "Error fetching data");
      setData(null);
      return null;
    } finally {
      if (signal && !signal.aborted) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    const tick = async () => {
      if (!cancelled) await refetch(controller.signal);
    };

    tick();
    const id = setInterval(tick, intervalMs);

    return () => {
      cancelled = true;
      controller.abort();
      clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, intervalMs]);

  return { data, loading, error, refetch };
};
