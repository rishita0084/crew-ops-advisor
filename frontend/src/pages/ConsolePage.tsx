import React, { useEffect, useRef, useState } from 'react';
import { ArrowUp } from 'lucide-react';
import { AskBar } from '../components/ask/AskBar';
import { SuggestedQuestions } from '../components/ask/SuggestedQuestions';
import { AnswerCard } from '../components/answer/AnswerCard';
import { AnswerSkeleton } from '../components/common/Skeleton';
import { AlertsRail } from '../components/alerts/AlertsRail';
import { WhatIfPanel } from '../components/whatif/WhatIfPanel';
import { useAdvisor } from '../hooks/useAdvisor';
import { useAlerts } from '../hooks/useAlerts';

export function ConsolePage() {
  const { thread, pending, ask, runWhatIf } = useAdvisor();
  const { alerts, loading, error } = useAlerts();
  const endRef = useRef<HTMLDivElement>(null);
  const [showScrollToTop, setShowScrollToTop] = useState(false);
  const started = thread.length > 0;

  useEffect(() => {
    const updateVisibility = () => setShowScrollToTop(window.scrollY > 300);

    updateVisibility();
    window.addEventListener('scroll', updateVisibility, { passive: true });
    return () => window.removeEventListener('scroll', updateVisibility);
  }, []);

  useEffect(() => {
    if (thread.length === 0) return;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    endRef.current?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'end' });
  }, [thread]);

  const scrollToTop = () => {
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    window.scrollTo({ top: 0, behavior: reduced ? 'auto' : 'smooth' });
  };

  return (
    <div className="mx-auto grid w-full max-w-page gap-8 px-5 py-8 xl:grid-cols-[minmax(0,1fr)_var(--width-rail)]">
      <main className="mx-auto w-full max-w-console">
        <h1 className="sr-only">Crew operations advisor console</h1>
        <div className={started ? '' : 'pt-10 sm:pt-16'}>
          <AskBar onAsk={ask} pending={pending} compact={started} />
          {!started && <SuggestedQuestions onSelect={ask} disabled={pending} />}
        </div>

        <div className="mt-5">
          <WhatIfPanel onSimulate={runWhatIf} disabled={pending} />
        </div>

        {started &&
        <section aria-label="Conversation" aria-live="polite" className="mt-8 space-y-8">
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
                  {!exchange.error && exchange.response && <AnswerCard response={exchange.response} />}
                </div>
              </article>
          )}
            <div ref={endRef} />
          </section>
        }

        {showScrollToTop &&
        <div className="pointer-events-none fixed inset-x-0 bottom-5 z-50 sm:bottom-8">
            <div className="mx-auto grid w-full max-w-page gap-8 px-5 xl:grid-cols-[minmax(0,1fr)_var(--width-rail)]">
              <div className="mx-auto flex w-full max-w-console justify-center">
                <button
                  type="button"
                  onClick={scrollToTop}
                  className="pointer-events-auto flex items-center gap-2 rounded-full border border-accent-line bg-accent px-4 py-2.5 text-sm font-semibold text-accent-ink shadow-card transition-colors duration-150 ease-out hover:bg-accent-strong"
                >
                  <ArrowUp aria-hidden="true" className="h-4 w-4" />
                  Scroll to Top
                </button>
              </div>
            </div>
          </div>
        }
      </main>

      <div className="xl:sticky xl:top-8 xl:self-start">
        <AlertsRail alerts={alerts} loading={loading} error={error} />
      </div>

    </div>);

}
