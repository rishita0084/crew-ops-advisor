import React from 'react';
import { AlertItem } from './AlertItem';
import { Skeleton } from '../common/Skeleton';
import type { Alert } from '../../types/api';

interface AlertsRailProps {
  alerts: Alert[];
  loading: boolean;
  error: string | null;
}

export function AlertsRail({ alerts, loading, error }: AlertsRailProps) {
  return (
    <aside
      aria-label="Operational warnings"
      className="rounded-xl border border-line bg-surface shadow-card">
      
      <div className="flex items-baseline justify-between gap-3 px-5 py-4">
        <h2 className="text-2xs font-semibold uppercase tracking-label text-fg-faint">Watch list</h2>
        {!loading && !error &&
        <span className="font-mono text-2xs text-fg-faint">{alerts.length}</span>
        }
      </div>

      {loading &&
      <div className="space-y-4 border-t border-line px-5 py-4" role="status" aria-live="polite">
          <span className="sr-only">Loading operational warnings</span>
          {[0, 1, 2].map((index) =>
        <div key={index} className="space-y-2">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-4/5" />
            </div>
        )}
        </div>
      }

      {!loading && error &&
      <p className="border-t border-line px-5 py-4 text-sm text-fg-muted">{error}</p>
      }

      {!loading && !error && alerts.length === 0 &&
      <p className="border-t border-line px-5 py-4 text-sm text-fg-muted">
          Nothing needs attention right now.
        </p>
      }

      {!loading && !error && alerts.length > 0 &&
      <ul className="border-t border-line">
          {alerts.map((alert) =>
        <AlertItem key={alert.id} alert={alert} />
        )}
        </ul>
      }
    </aside>);

}