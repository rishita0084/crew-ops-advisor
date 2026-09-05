import { useEffect, useState } from 'react';
import { getAlerts } from '../services/api';
import type { Alert } from '../types/api';

export function useAlerts(date?: string) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    getAlerts(date).
    then((res) => {
      if (!active) return;
      setAlerts(res.alerts || []);
      setError(null);
    }).
    catch(() => {
      if (active) setError('Alerts are unavailable.');
    }).
    finally(() => {
      if (active) setLoading(false);
    });
    return () => {
      active = false;
    };
  }, [date]);

  return { alerts, loading, error };
}