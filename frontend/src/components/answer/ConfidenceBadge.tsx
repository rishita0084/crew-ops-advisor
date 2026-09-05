import React from 'react';
import { CheckCircle2Icon, CircleSlashIcon, EyeIcon } from 'lucide-react';
import { Badge } from '../common/Badge';
import type { Confidence } from '../../types/api';

const map: Record<Confidence, {label: string;tone: 'pass' | 'warning' | 'neutral';icon: React.ReactNode;title: string;}> = {
  high: {
    label: 'High confidence',
    tone: 'pass',
    icon: <CheckCircle2Icon aria-hidden="true" className="h-3.5 w-3.5" />,
    title: 'Every value in this answer came from a rule check or a data lookup.'
  },
  review: {
    label: 'Review before acting',
    tone: 'warning',
    icon: <EyeIcon aria-hidden="true" className="h-3.5 w-3.5" />,
    title: 'Part of this answer needs a controller to confirm it.'
  },
  cannot_answer: {
    label: 'Cannot answer',
    tone: 'neutral',
    icon: <CircleSlashIcon aria-hidden="true" className="h-3.5 w-3.5" />,
    title: 'The data required to answer this is not held.'
  }
};

export function ConfidenceBadge({ confidence }: {confidence: Confidence;}) {
  const item = map[confidence];
  return (
    <Badge tone={item.tone} icon={item.icon} title={item.title}>
      {item.label}
    </Badge>);

}