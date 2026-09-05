import React from 'react';
import type { EvidenceItem } from '../../types/api';

const SOURCE_LABELS: Record<string, string> = {
  crew: 'Crew record',
  flights: 'Flight schedule',
  pairings: 'Pairings',
  pairing_crew: 'Pairing assignments',
  pairing_day_flights: 'Pairing day legs',
  duty_clocks: 'Duty clocks',
  duty_history: 'Duty history',
  reserve_pool: 'Reserve pool',
  certifications: 'Certifications',
  rules: 'Rule book',
  costs: 'Cost table',
  risk_signals: 'Risk signals',
  legality_matrix: 'Legality matrix'
};

function label(source: string): string {
  return SOURCE_LABELS[source] || source.replace(/_/g, ' ');
}

export function EvidenceList({ items }: {items: EvidenceItem[];}) {
  return (
    <dl className="divide-y divide-line rounded-md border border-line bg-sunken">
      {items.map((item, index) =>
      <div key={index} className="grid gap-1 px-4 py-3 sm:grid-cols-[9rem_1fr_auto] sm:items-baseline sm:gap-4">
          <dt className="text-2xs font-semibold uppercase tracking-label text-fg-faint">
            {label(item.source)}
          </dt>
          <dd className="text-sm text-fg-muted">{item.fact}</dd>
          <dd className="font-mono text-xs text-fg sm:text-right">{item.value}</dd>
        </div>
      )}
    </dl>);

}