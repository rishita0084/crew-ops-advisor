import React, { useId, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ChevronDownIcon } from 'lucide-react';
import { Badge } from '../common/Badge';
import { RuleCheckList } from './RuleCheckList';
import { CostBreakdown } from './CostBreakdown';
import { ResilienceMeter } from './ResilienceMeter';
import { ChainSteps } from './ChainSteps';
import { formatInr, formatMinutes } from '../../utils/format';
import type { RecoveryOption } from '../../types/api';

interface OptionCardProps {
  option: RecoveryOption;
  recommended: boolean;
}

export function OptionCard({ option, recommended }: OptionCardProps) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const fullCoverage = option.uncovered_flight_ids.length === 0;

  return (
    <li
      className={`overflow-hidden rounded-lg border ${
      recommended ? 'border-accent-line bg-surface' : 'border-line bg-surface'}`
      }>
      
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
        className="w-full px-5 py-5 text-left transition-colors duration-150 ease-out hover:bg-raised">
        
        <div className="flex items-start gap-4">
          <span
            className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full font-mono text-sm ${
            recommended ?
            'bg-accent text-accent-ink' :
            'border border-line-strong bg-raised text-fg-muted'}`
            }>
            
            {option.rank}
          </span>

          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              {recommended &&
              <span className="text-2xs font-semibold uppercase tracking-label text-accent">
                  Recommended
                </span>
              }
              <Badge tone={option.legal ? 'pass' : 'danger'}>
                {option.legal ? 'Legal' : 'Not legal'}
              </Badge>
              <Badge tone={fullCoverage ? 'neutral' : 'warning'}>{option.coverage}</Badge>
              {option.delay_minutes > 0 &&
              <Badge tone="warning">{formatMinutes(option.delay_minutes)} delay</Badge>
              }
            </div>

            <p
              className={`mt-3 leading-snug text-fg ${
              recommended ? 'text-md font-medium' : 'text-base'}`
              }>
              
              {option.action}
            </p>
            <p className="mt-2 text-sm leading-relaxed text-fg-muted">{option.reasoning}</p>

            {option.uncovered_flight_ids.length > 0 &&
            <p className="mt-2 font-mono text-2xs text-warning">
                Uncovered: {option.uncovered_flight_ids.join(', ')}
              </p>
            }
          </div>

          <div className="flex shrink-0 flex-col items-end gap-2">
            <span className="font-mono text-md text-fg">{formatInr(option.cost_inr)}</span>
            <span className="flex items-center gap-1 text-2xs uppercase tracking-label text-fg-faint">
              {open ? 'Hide' : 'Why'}
              <ChevronDownIcon
                aria-hidden="true"
                className={`h-3.5 w-3.5 transition-transform duration-150 ease-out ${open ? 'rotate-180' : ''}`} />
              
            </span>
          </div>
        </div>
      </button>

      <AnimatePresence initial={false}>
        {open &&
        <motion.div
          id={panelId}
          key="panel"
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.22, ease: [0.23, 1, 0.32, 1] }}
          className="overflow-hidden border-t border-line">
          
            <div className="space-y-5 px-5 py-5">
              <div>
                <h4 className="mb-2 text-2xs font-semibold uppercase tracking-label text-fg-faint">
                  Rule checks · {option.rules_checked.length} evaluated
                </h4>
                <RuleCheckList checks={option.rule_checks} />
              </div>

              {option.chain.length > 1 &&
            <div>
                  <h4 className="mb-2 text-2xs font-semibold uppercase tracking-label text-fg-faint">
                    Swap cascade · {option.chain.length} moves
                  </h4>
                  <ChainSteps steps={option.chain} />
                </div>
            }

              <div className="grid gap-4 lg:grid-cols-2">
                <div>
                  <h4 className="mb-2 text-2xs font-semibold uppercase tracking-label text-fg-faint">
                    Cost
                  </h4>
                  <CostBreakdown items={option.cost_breakdown} total={option.cost_inr} />
                </div>
                <div>
                  <h4 className="mb-2 text-2xs font-semibold uppercase tracking-label text-fg-faint">
                    Resilience
                  </h4>
                  <ResilienceMeter score={option.resilience_score} note={option.resilience_note} />
                </div>
              </div>
            </div>
          </motion.div>
        }
      </AnimatePresence>
    </li>);

}