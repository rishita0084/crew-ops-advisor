import React from 'react';
import { ArrowRightIcon } from 'lucide-react';
import type { Relaxation } from '../../types/api';

export function RelaxationCard({ relaxation }: {relaxation: Relaxation;}) {
  return (
    <li className="rounded-lg border border-warning-line bg-surface p-5">
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-mono text-xs text-warning">{relaxation.rule_id}</span>
        <span className="rounded-full border border-warning-line bg-warning-soft px-3 py-1 text-2xs font-medium text-warning">
          {relaxation.breach_magnitude}
        </span>
      </div>
      <p className="mt-3 text-sm leading-relaxed text-fg-muted">{relaxation.breach_detail}</p>
      <div className="mt-4 flex items-start gap-2 rounded-md border border-line bg-sunken px-4 py-3">
        <ArrowRightIcon aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
        <div>
          <p className="text-2xs font-semibold uppercase tracking-label text-fg-faint">
            To make it legal
          </p>
          <p className="mt-1 text-sm text-fg">{relaxation.remedy}</p>
          {relaxation.resulting_option_rank !== null &&
          <p className="mt-1 text-xs text-fg-faint">
              Becomes option {relaxation.resulting_option_rank} once applied.
            </p>
          }
        </div>
      </div>
    </li>);

}