import { useEffect, useState } from 'react';
import { CheckIcon, CopyIcon, SendIcon, TriangleAlertIcon } from 'lucide-react';
import type { NotificationDraft as Draft } from '../../types/api';

/**
 * A drafted crew message, shown for review.
 *
 * Deliberately not sendable. The dataset carries no contact details for any crew member,
 * so "sending" would mean inventing an address -- the exact class of fabrication this
 * system is built to prevent. Delivery belongs to the airline's crew-comms system; the
 * advisor's job ends at a correct, complete draft.
 */
export function NotificationDraft({ draft }: {draft: Draft;}) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 2000);
    return () => window.clearTimeout(timer);
  }, [copied]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(draft.message);
      setCopied(true);
    } catch {
      // clipboard is blocked outside a secure context; the text is selectable anyway
      setCopied(false);
    }
  };

  return (
    <section
      aria-label={`Draft callout for ${draft.crew_id}`}
      className="overflow-hidden rounded-md border border-line bg-sunken">

      <header className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
        <h3 className="text-2xs font-semibold uppercase tracking-label text-fg-muted">
          Draft callout · {draft.crew_id} · {draft.pairing_id}
        </h3>
        <span className="rounded-full border border-line-strong px-2 py-0.5 text-2xs text-fg-faint">
          Not sent
        </span>
      </header>

      <pre className="overflow-x-auto px-4 py-4 font-mono text-xs leading-relaxed text-fg">
        {draft.message}
      </pre>

      {!draft.legal &&
      <div className="mx-4 mb-3 flex items-start gap-2 rounded-md border border-warning-line bg-warning-soft px-3 py-2">
          <TriangleAlertIcon aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
          <p className="text-xs text-fg">
            This assignment did not pass every rule. Resolve the exceedance before sending.
          </p>
        </div>
      }

      <footer className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-3">
        <button
          type="button"
          onClick={copy}
          className="inline-flex items-center gap-1.5 rounded-full bg-accent px-3.5 py-1.5 text-xs font-semibold text-accent-ink transition-colors duration-150 ease-out hover:bg-accent-strong">

          {copied ?
          <CheckIcon aria-hidden="true" className="h-3.5 w-3.5" /> :
          <CopyIcon aria-hidden="true" className="h-3.5 w-3.5" />}
          {copied ? 'Copied' : 'Copy message'}
        </button>

        <button
          type="button"
          disabled
          title="dCortex Air crew comms integration is not connected in this prototype."
          className="inline-flex cursor-not-allowed items-center gap-1.5 rounded-full border border-line px-3.5 py-1.5 text-xs text-fg-faint">

          <SendIcon aria-hidden="true" className="h-3.5 w-3.5" />
          Send via crew comms
        </button>

        <p className="ml-auto text-2xs text-fg-faint">
          Draft only — crew comms integration not connected
        </p>
      </footer>
    </section>);

}
