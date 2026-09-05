import React, { useEffect, useRef, useState } from 'react';
import { ArrowUpIcon } from 'lucide-react';

interface AskBarProps {
  onAsk: (question: string) => void;
  pending: boolean;
  compact: boolean;
}

export function AskBar({ onAsk, pending, compact }: AskBarProps) {
  const [value, setValue] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || pending) return;
    onAsk(trimmed);
    setValue('');
  };

  return (
    <form onSubmit={submit}>
      <label
        htmlFor="ask-input"
        className={`block font-semibold tracking-tightest text-fg ${
        compact ? 'text-base' : 'text-2xl sm:text-3xl'}`
        }>
        
        What happened?
      </label>
      {!compact &&
      <p className="mt-2 text-sm text-fg-muted">
          Describe the disruption in your own words. One question, one answer, one decision.
        </p>
      }

      <div className="relative mt-4">
        <input
          id="ask-input"
          ref={inputRef}
          type="text"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          autoComplete="off"
          placeholder="Captain C-2087 has called in sick for today…"
          className="w-full rounded-full border border-line bg-surface py-4 pl-6 pr-16 text-base text-fg shadow-card placeholder:text-fg-faint" />
        
        <button
          type="submit"
          disabled={pending || value.trim().length === 0}
          aria-label="Ask the advisor"
          className="absolute right-2 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full bg-accent text-accent-ink transition-colors duration-150 ease-out hover:bg-accent-strong disabled:bg-raised disabled:text-fg-faint">
          
          <ArrowUpIcon aria-hidden="true" className="h-5 w-5" />
        </button>
      </div>
    </form>);

}