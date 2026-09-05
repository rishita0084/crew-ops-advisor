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
 * Two panels: a wide one for the conversation, a narrow one for the watch list.
 *
 * Both are the same rounded, bordered surface so the screen reads as two organised
 * regions rather than text floating on a page. Depth runs page -> panel -> card, so an
 * answer sits visibly *on* the conversation panel instead of merging into it.
 *
 * The conversation panel has two states. Before the first question the ask bar sits
 * centred with the suggestions under it and nothing competes for attention. Once a
 * conversation starts the ask bar becomes a fixed footer inside the panel and only the
 * transcript scrolls — a controller mid-disruption should never scroll to reach the
 * input, or lose the answer they are reading because a new one arrived.
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
    <div className="mx-auto grid w-full max-w-page gap-4 px-4 py-4 sm:px-5 sm:py-5 lg:h-full lg:min-h-0 lg:grid-cols-[minmax(0,1fr)_var(--width-rail)] lg:gap-5">
      {/* ---------------- conversation panel ---------------- */}
      <main className="flex w-full flex-col overflow-hidden rounded-xl border border-line bg-surface shadow-card lg:h-full lg:min-h-0">
        <h1 className="sr-only">Crew operations advisor console</h1>

        {started ?
        <>
            {/* the only part of this panel that scrolls */}
            <section
            aria-label="Conversation"
            aria-live="polite"
            className="flex-1 space-y-8 overflow-y-auto px-4 py-6 sm:px-6 lg:min-h-0">

              <div className="mx-auto w-full max-w-console space-y-8">
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
              </div>
            </section>

            {/* footer well: always reachable, never scrolls away */}
            <div className="shrink-0 border-t border-line bg-sunken px-4 py-4 sm:px-6">
              <div className="mx-auto w-full max-w-console space-y-3">
                <AskBar onAsk={ask} pending={pending} compact />
                <WhatIfPanel onSimulate={runWhatIf} disabled={pending} />
              </div>
            </div>
          </> :

        <div className="flex flex-1 flex-col justify-center overflow-y-auto px-4 py-10 sm:px-6 sm:py-16">
            <div className="mx-auto w-full max-w-console">
              <AskBar onAsk={ask} pending={pending} compact={false} />
              <SuggestedQuestions onSelect={ask} disabled={pending} />
              <div className="mt-5">
                <WhatIfPanel onSimulate={runWhatIf} disabled={pending} />
              </div>
            </div>
          </div>
        }
      </main>

      {/* ---------------- watch list panel ---------------- */}
      {/* AlertsRail brings its own panel shell, matching the one above */}
      <div className="w-full lg:h-full lg:min-h-0 lg:overflow-y-auto">
        <AlertsRail alerts={alerts} loading={loading} error={error} />
      </div>
    </div>);

}
