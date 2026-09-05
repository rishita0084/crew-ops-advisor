import React, { useId, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ChevronDownIcon, FlaskConicalIcon } from 'lucide-react';

interface WhatIfPanelProps {
  onSimulate: (question: string) => void;
  disabled: boolean;
}

export function WhatIfPanel({ onSimulate, disabled }: WhatIfPanelProps) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState('');
  const panelId = useId();
  const inputId = useId();

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSimulate(trimmed);
    setValue('');
  };

  return (
    <div className="rounded-lg border border-line bg-surface">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-5 py-3 text-left transition-colors duration-150 ease-out hover:bg-raised">
        
        <span className="flex items-center gap-2 text-sm text-fg-muted">
          <FlaskConicalIcon aria-hidden="true" className="h-4 w-4 text-info" />
          Test a change before you make it
        </span>
        <ChevronDownIcon
          aria-hidden="true"
          className={`h-4 w-4 shrink-0 text-fg-faint transition-transform duration-150 ease-out ${
          open ? 'rotate-180' : ''}`
          } />
        
      </button>

      <AnimatePresence initial={false}>
        {open &&
        <motion.div
          id={panelId}
          key="panel"
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
          className="overflow-hidden border-t border-line">
          
            <form onSubmit={submit} className="px-5 py-4">
              <label htmlFor={inputId} className="text-2xs font-semibold uppercase tracking-label text-fg-faint">
                Hypothetical
              </label>
              <div className="mt-2 flex flex-col gap-3 sm:flex-row">
                <input
                id={inputId}
                type="text"
                value={value}
                onChange={(event) => setValue(event.target.value)}
                placeholder="What if I move C-2087 onto DX412?"
                className="min-w-0 flex-1 rounded-full border border-line bg-sunken px-5 py-2.5 text-sm text-fg placeholder:text-fg-faint" />
              
                <button
                type="submit"
                disabled={disabled || value.trim().length === 0}
                className="rounded-full bg-accent px-5 py-2.5 text-sm font-semibold text-accent-ink transition-colors duration-150 ease-out hover:bg-accent-strong disabled:bg-raised disabled:text-fg-faint">
                
                  Run simulation
                </button>
              </div>
              <p className="mt-2 text-xs text-fg-faint">
                Nothing is applied to the live roster. You will see a before and after only.
              </p>
            </form>
          </motion.div>
        }
      </AnimatePresence>
    </div>);

}