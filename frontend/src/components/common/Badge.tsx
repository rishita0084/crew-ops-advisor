import React from 'react';

export type BadgeTone = 'neutral' | 'accent' | 'pass' | 'warning' | 'danger' | 'info';

interface BadgeProps {
  children: React.ReactNode;
  tone?: BadgeTone;
  icon?: React.ReactNode;
  solid?: boolean;
  title?: string;
}

const toneClass: Record<BadgeTone, string> = {
  neutral: 'bg-raised border-line text-fg-muted',
  accent: 'bg-accent-soft border-accent-line text-accent',
  pass: 'bg-pass-soft border-accent-line text-pass',
  warning: 'bg-warning-soft border-warning-line text-warning',
  danger: 'bg-danger-soft border-danger-line text-danger',
  info: 'bg-info-soft border-info-line text-info'
};

export function Badge({ children, tone = 'neutral', icon, solid = false, title }: BadgeProps) {
  return (
    <span
      title={title}
      className={`inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-3 py-1 text-xs font-medium ${
      solid ? 'border-accent bg-accent text-accent-ink' : toneClass[tone]}`
      }>
      
      {icon}
      {children}
    </span>);

}