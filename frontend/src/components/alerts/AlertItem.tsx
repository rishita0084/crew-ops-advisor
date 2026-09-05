import React from 'react';
import { AlertTriangleIcon, InfoIcon, OctagonAlertIcon } from 'lucide-react';
import type { Alert } from '../../types/api';

const severityStyle: Record<Alert['severity'], {dot: string;text: string;icon: React.ReactNode;}> = {
  critical: {
    dot: 'border-danger-line bg-danger-soft',
    text: 'text-danger',
    icon: <OctagonAlertIcon aria-hidden="true" className="h-3.5 w-3.5" />
  },
  warning: {
    dot: 'border-warning-line bg-warning-soft',
    text: 'text-warning',
    icon: <AlertTriangleIcon aria-hidden="true" className="h-3.5 w-3.5" />
  },
  info: {
    dot: 'border-info-line bg-info-soft',
    text: 'text-info',
    icon: <InfoIcon aria-hidden="true" className="h-3.5 w-3.5" />
  }
};

const subjectLabel: Record<Alert['subject_type'], string> = {
  crew: 'Crew',
  flight: 'Flight',
  station: 'Station',
  pool: 'Pool'
};

export function AlertItem({ alert }: {alert: Alert;}) {
  const style = severityStyle[alert.severity];

  return (
    <li className="border-t border-line px-5 py-4 first:border-t-0">
      <div className="flex items-center gap-2">
        <span
          className={`flex h-5 w-5 items-center justify-center rounded-full border ${style.dot} ${style.text}`}>
          
          {style.icon}
        </span>
        <span className={`text-2xs font-semibold uppercase tracking-label ${style.text}`}>
          {alert.severity}
        </span>
        <span className="ml-auto text-2xs text-fg-faint">{subjectLabel[alert.subject_type]}</span>
      </div>
      <p className="mt-2 font-mono text-xs text-fg">{alert.subject}</p>
      <p className="mt-1 text-sm leading-relaxed text-fg-muted">{alert.message}</p>
    </li>);

}