import React from 'react';
import { RuleCheckList } from './RuleCheckList';
import type { ChainStep } from '../../types/api';

export function ChainSteps({ steps }: {steps: ChainStep[];}) {
  return (
    <ol className="space-y-3">
      {steps.map((step) =>
      <li key={step.step} className="relative rounded-md border border-line pl-12 pr-4 py-3">
          <span className="absolute left-4 top-3 flex h-6 w-6 items-center justify-center rounded-full border border-accent-line bg-accent-soft font-mono text-2xs text-accent">
            {step.step}
          </span>
          <p className="text-sm text-fg">{step.action}</p>
          <p className="mt-1 font-mono text-2xs text-fg-faint">
            {step.crew_id}
            {step.pairing_id ? ` → ${step.pairing_id}` : ''}
            {step.flight_ids.length > 0 ? ` · ${step.flight_ids.join(', ')}` : ''}
          </p>
          {step.rule_checks.length > 0 &&
        <div className="mt-3">
              <RuleCheckList checks={step.rule_checks} />
            </div>
        }
        </li>
      )}
    </ol>);

}