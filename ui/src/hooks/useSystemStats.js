import { useState, useEffect } from 'react';

/**
 * Polls /api/system every 5 seconds for live system stats.
 */
export function useSystemStats(interval = 5000) {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let mounted = true;

    const fetchStats = async () => {
      try {
        const res = await fetch('/api/system');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (mounted) {
          setStats(data);
          setError(null);
        }
      } catch (err) {
        if (mounted) setError(err.message);
      }
    };

    fetchStats();
    const timer = setInterval(fetchStats, interval);
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, [interval]);

  return { stats, error };
}
