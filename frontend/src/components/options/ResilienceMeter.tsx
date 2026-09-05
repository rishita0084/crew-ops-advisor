import React from 'react';

interface ResilienceMeterProps {
  score: number;
  note: string;
}

export function ResilienceMeter({ score, note }: ResilienceMeterProps) {
  const bounded = Math.max(0, Math.min(100, score));
  const tone = bounded >= 70 ? 'bg-accent' : bounded >= 50 ? 'bg-warning' : 'bg-danger';

  return (
    <div className="rounded-md border border-line px-4 py-3">
      <div className="flex items-baseline justify-between gap-4">
        <span className="text-2xs font-semibold uppercase tracking-label text-fg-faint">
          Recovery capacity left
        </span>
        <span className="font-mono text-sm text-fg">{bounded}</span>
      </div>
      <div
        className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-raised"
        role="meter"
        aria-valuenow={bounded}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Recovery capacity remaining after this decision">
        
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${bounded}%` }} />
      </div>
      <p className="mt-2 text-xs leading-relaxed text-fg-muted">{note}</p>
    </div>);

}