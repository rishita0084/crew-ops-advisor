import React from 'react';
import { CircleSlashIcon } from 'lucide-react';
import { Card } from '../common/Card';
import { Expandable } from '../common/Expandable';
import { EvidenceList } from './EvidenceList';
import type { AdvisorResponse } from '../../types/api';

/** Deliberate, trustworthy non-answer — not an error state. */
export function CannotAnswerCard({ response }: {response: AdvisorResponse;}) {
  return (
    <Card as="article" tone="quiet">
      <div className="p-6">
        <div className="flex items-center gap-2 text-2xs font-semibold uppercase tracking-label text-fg-faint">
          <CircleSlashIcon aria-hidden="true" className="h-3.5 w-3.5" />
          No answer available
        </div>
        <p className="mt-4 text-md leading-relaxed text-fg">{response.answer_text}</p>

        {response.evidence.length > 0 &&
        <div className="mt-6">
            <h3 className="text-2xs font-semibold uppercase tracking-label text-fg-faint">
              What was checked
            </h3>
            <ul className="mt-3 divide-y divide-line rounded-md border border-line">
              {response.evidence.map((item, index) =>
            <li key={index} className="flex items-baseline justify-between gap-4 px-4 py-3">
                  <span className="text-sm text-fg-muted">{item.fact}</span>
                  <span className="shrink-0 font-mono text-xs text-fg">{item.value}</span>
                </li>
            )}
            </ul>
          </div>
        }
      </div>
      {response.evidence.length > 0 &&
      <Expandable label="Show evidence" count={response.evidence.length}>
          <EvidenceList items={response.evidence} />
        </Expandable>
      }
    </Card>);

}