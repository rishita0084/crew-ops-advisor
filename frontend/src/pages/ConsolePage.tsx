import { useEffect, useRef } from 'react';
import { AskBar } from '../components/ask/AskBar';
import { SuggestedQuestions } from '../components/ask/SuggestedQuestions';
import { AnswerCard } from '../components/answer/AnswerCard';
import { AnswerSkeleton } from '../components/common/Skeleton';
import { AlertsRail } from '../components/alerts/AlertsRail';
import { WhatIfPanel } from '../components/whatif/WhatIfPanel';
import { useAdvisor } from '../hooks/useAdvisor';
import { useAlerts } from '../hooks/useAlerts';

/**
 * Two states, deliberately different shapes.
 *
 * Before the first question the ask bar sits centred with the suggestions under it —
 * nothing else competes for attention. Once a conversation starts it drops to the bottom
 * and stays there, and only the transcript scrolls. A controller mid-disruption should
 * never have to scroll back up to reach the input, or lose the answer they are reading
 * because a new one arrived.
 */
export function ConsolePage() {
  const { thread, pending, ask, runWhatIf } = useAdvisor();
  const { alerts, loading, error } = useAlerts();
  const endRef = useRef<HTMLDivElement>(null);
  const started = thread.length > 0;

  useEffect(() => {
    if (thread.length === 0) return;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    endRef.current?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'end' });
  }, [thread]);

  return (
    <div className="mx-auto grid w-full max-w-page gap-6 px-5 lg:h-full lg:min-h-0 lg:grid-cols-[minmax(0,1fr)_var(--width-rail)] lg:gap-8">
      {/* ---------------- conversation column ---------------- */}
      <main className="flex w-full flex-col lg:h-full lg:min-h-0">
        <h1 className="sr-only">Crew operations advisor console</h1>

        {started ?
        <>
            {/* only this scrolls */}
            <section
            aria-label="Conversation"
            aria-live="polite"
            className="mx-auto w-full max-w-console space-y-8 py-8 lg:min-h-0 lg:flex-1 lg:overflow-y-auto">

              {thread.map((exchange) =>
            <article key={exchange.id}>
                  <div className="border-l-2 border-accent pl-4">
                    <p className="text-2xs font-semibold uppercase tracking-label text-fg-faint">
                      {exchange.kind === 'what_if' ? 'Hypothetical' : 'Asked'}
                    </p>
                    <h2 className="mt-1 text-base text-fg">{exchange.question}</h2>
                  </div>

                  <div className="mt-4">
                    {exchange.error &&
                <div className="rounded-lg border border-danger-line bg-danger-soft px-5 py-4 text-sm text-danger">
                        {exchange.error}
                      </div>
                }
                    {!exchange.error && !exchange.response && <AnswerSkeleton />}
                    {!exchange.error && exchange.response &&
                <AnswerCard response={exchange.response} />
                }
                  </div>
                </article>
            )}
              <div ref={endRef} />
            </section>

            {/* pinned: always reachable, never scrolls away */}
            <div className="shrink-0 border-t border-line bg-void pb-6 pt-4">
              <div className="mx-auto w-full max-w-console space-y-3">
                <AskBar onAsk={ask} pending={pending} compact />
                <WhatIfPanel onSimulate={runWhatIf} disabled={pending} />
              </div>
            </div>
          </> :

        <div className="mx-auto flex w-full max-w-console flex-1 flex-col justify-center py-10 sm:py-16">
            <AskBar onAsk={ask} pending={pending} compact={false} />
            <SuggestedQuestions onSelect={ask} disabled={pending} />
            <div className="mt-5">
              <WhatIfPanel onSimulate={runWhatIf} disabled={pending} />
            </div>
          </div>
        }
      </main>

      {/* ---------------- watch list ---------------- */}
      {/* a plain div: AlertsRail is itself the <aside> landmark */}
      <div className="w-full pb-8 lg:h-full lg:min-h-0 lg:overflow-y-auto lg:py-8">
        <AlertsRail alerts={alerts} loading={loading} error={error} />
      </div>
    </div>);

}
