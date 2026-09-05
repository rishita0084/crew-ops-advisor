import React from 'react';

interface CardProps {
  children: React.ReactNode;
  as?: 'div' | 'section' | 'article' | 'li';
  tone?: 'default' | 'raised' | 'quiet';
  className?: string;
}

const toneClass: Record<NonNullable<CardProps['tone']>, string> = {
  default: 'bg-surface border-line',
  raised: 'bg-raised border-line-strong',
  quiet: 'bg-sunken border-line'
};

export function Card({ children, as = 'div', tone = 'default', className = '' }: CardProps) {
  const Tag = as;
  return (
    <Tag className={`rounded-lg border ${toneClass[tone]} shadow-card ${className}`}>{children}</Tag>);

}