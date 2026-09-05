import React from 'react';
import { OptionCard } from './OptionCard';
import type { RecoveryOption } from '../../types/api';

export function OptionList({ options }: {options: RecoveryOption[];}) {
  const sorted = [...options].sort((a, b) => a.rank - b.rank);

  return (
    <section aria-label="Ranked recovery options">
      <h3 className="mb-3 text-2xs font-semibold uppercase tracking-label text-fg-faint">
        Options · ranked
      </h3>
      <ul className="space-y-3">
        {sorted.map((option, index) =>
        <OptionCard key={option.rank} option={option} recommended={index === 0} />
        )}
      </ul>
    </section>);

}