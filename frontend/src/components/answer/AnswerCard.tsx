import React from 'react';
import { ShieldAlertIcon } from 'lucide-react';
import { Card } from '../common/Card';
import { Expandable } from '../common/Expandable';
import { ConfidenceBadge } from './ConfidenceBadge';
import { GroundingBadge } from './GroundingBadge';
import { CannotAnswerCard } from './CannotAnswerCard';
import { EvidenceList } from './EvidenceList';
import { NotificationDraft } from './NotificationDraft';
import { ResultTable } from '../table/ResultTable';
import { ImpactGraph } from '../impact/ImpactGraph';
import { OptionList } from '../options/OptionList';
import { RelaxationCard } from '../options/RelaxationCard';
import { BeforeAfterDiff } from '../whatif/BeforeAfterDiff';
import { AlertItem } from '../alerts/AlertItem';
import type { AdvisorResponse } from '../../types/api';

export function AnswerCard({ response }: {response: AdvisorResponse;}) {
  if (response.confidence === 'cannot_answer') {
    return <CannotAnswerCard response={response} />;
  }

  const unverified = response.grounding.unverified_claims;

  return (
    <Card as="article">
      <div className="p-6">
        <div className="flex flex-wrap items-center gap-2">
          <ConfidenceBadge confidence={response.confidence} />
          <GroundingBadge verified={response.grounding.verified} unverifiedCount={unverified.length} />
        </div>

        <p className="mt-5 text-md leading-relaxed text-fg sm:text-lg sm:leading-relaxed">
          {response.answer_text}
        </p>

        {!response.grounding.verified && unverified.length > 0 &&
        <div className="mt-5 rounded-md border border-warning-line bg-warning-soft px-4 py-3">
            <div className="flex items-center gap-2">
              <ShieldAlertIcon aria-hidden="true" className="h-4 w-4 shrink-0 text-warning" />
              <p className="text-2xs font-semibold uppercase tracking-label text-warning">
                Not backed by operational data
              </p>
            </div>
            <ul className="mt-2 space-y-1">
              {unverified.map((claim, index) =>
            <li key={index} className="text-sm leading-relaxed text-fg">
                  “{claim}”
                </li>
            )}
            </ul>
            <p className="mt-2 text-xs text-fg-muted">
              Treat these statements as unconfirmed. Every other value came from a checked source.
            </p>
          </div>
        }

        {response.table &&
        <div className="mt-6">
            <ResultTable
            columns={response.table.columns}
            rows={response.table.rows}
            caption={response.answer_text} />
          
          </div>
        }

        {response.impact &&
        <div className="mt-6">
            <ImpactGraph impact={response.impact} />
          </div>
        }

        {response.before_after && response.before_after.length > 0 &&
        <div className="mt-6">
            <BeforeAfterDiff rows={response.before_after} />
          </div>
        }

        {response.options && response.options.length > 0 &&
        <div className="mt-6">
            <OptionList options={response.options} />
          </div>
        }

        {response.relaxations && response.relaxations.length > 0 &&
        <div className="mt-6">
            <h3 className="mb-1 text-2xs font-semibold uppercase tracking-label text-warning">
              {response.options && response.options.some((option) => option.legal) ?
              'Closest misses' :
              'No fully legal option'}
            </h3>
            <p className="mb-3 text-sm text-fg-muted">
              Who came nearest to being usable, and what would have to change for each to
              become legal. This is how much slack the operation actually has.
            </p>
            <ul className="space-y-3">
              {response.relaxations.map((relaxation, index) =>
            <RelaxationCard key={`${relaxation.rule_id}-${index}`} relaxation={relaxation} />
            )}
            </ul>
          </div>
        }

        {response.notification &&
        <div className="mt-6">
            <NotificationDraft draft={response.notification} />
          </div>
        }

        {response.alerts && response.alerts.length > 0 &&
        <div className="mt-6 overflow-hidden rounded-md border border-line">
            <ul>
              {response.alerts.map((alert) =>
            <AlertItem key={alert.id} alert={alert} />
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