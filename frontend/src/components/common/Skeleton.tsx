import React from 'react';

interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className = '' }: SkeletonProps) {
  return <div aria-hidden="true" className={`skeleton rounded-sm ${className}`} />;
}

export function AnswerSkeleton() {
  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-lg border border-line bg-surface p-6 shadow-card">
      
      <span className="sr-only">Working on the answer</span>
      <div className="flex items-center gap-2">
        <Skeleton className="h-5 w-24 rounded-full" />
        <Skeleton className="h-5 w-20 rounded-full" />
      </div>
      <div className="mt-5 space-y-3">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-11/12" />
        <Skeleton className="h-4 w-7/12" />
      </div>
      <div className="mt-6 space-y-2">
        <Skeleton className="h-12 w-full rounded-md" />
        <Skeleton className="h-12 w-10/12 rounded-md" />
      </div>
    </div>);

}