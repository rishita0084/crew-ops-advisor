import React from 'react';
import { formatInr } from '../../utils/format';

interface CostBreakdownProps {
  items: {label: string;amount_inr: number;}[];
  total: number;
}

export function CostBreakdown({ items, total }: CostBreakdownProps) {
  return (
    <div className="rounded-md border border-line">
      <ul className="divide-y divide-line">
        {items.map((item, index) =>
        <li key={index} className="flex items-baseline justify-between gap-4 px-4 py-2.5">
            <span className="text-sm text-fg-muted">{item.label}</span>
            <span className="font-mono text-xs text-fg">{formatInr(item.amount_inr)}</span>
          </li>
        )}
      </ul>
      <div className="flex items-baseline justify-between gap-4 border-t border-line-strong bg-sunken px-4 py-3">
        <span className="text-2xs font-semibold uppercase tracking-label text-fg-faint">Total</span>
        <span className="font-mono text-sm font-medium text-fg">{formatInr(total)}</span>
      </div>
    </div>);

}