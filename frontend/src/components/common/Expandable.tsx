import React, { useId, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ChevronDownIcon } from 'lucide-react';

interface ExpandableProps {
  label: string;
  children: React.ReactNode;
  count?: number;
  defaultOpen?: boolean;
}

export function Expandable({ label, children, count, defaultOpen = false }: ExpandableProps) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();

  return (
    <div className="border-t border-line">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-5 py-3 text-left text-sm font-medium text-fg-muted transition-colors duration-150 ease-out hover:text-fg">
        
        <span className="flex items-center gap-2">
          {label}
          {typeof count === 'number' && <span className="text-fg-faint">({count})</span>}
        </span>
        <ChevronDownIcon
          aria-hidden="true"
          className={`h-4 w-4 shrink-0 transition-transform duration-150 ease-out ${open ? 'rotate-180' : ''}`} />
        
      </button>
      <AnimatePresence initial={false}>
        {open &&
        <motion.div
          id={id}
          key="content"
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
          className="overflow-hidden">
          
            <div className="px-5 pb-5">{children}</div>
          </motion.div>
        }
      </AnimatePresence>
    </div>);

}