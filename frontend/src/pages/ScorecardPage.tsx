import React, { useEffect, useState } from 'react';
import { getScorecard } from '../services/api';
import { Skeleton } from '../components/common/Skeleton';
import { formatTimestamp } from '../utils/format';
import type { ScorecardResponse } from '../types/api';

export function ScorecardPage() {
  const [data, setData] = useState<ScorecardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getScorecard().
    then((res) => {
      if (active) setData(res);
    }).
    catch(() => {
      if (active) setError('The scorecard could not be loaded.');
    });
    return () => {
      active = false;
    };
  }, []);

  const questionsPassed = data ? data.tiers.reduce((sum, tier) => sum + tier.passed, 0) : 0;
  const questionsTotal = data ? data.tiers.reduce((sum, tier) => sum + tier.total, 0) : 0;

  return (
    <main className="mx-auto w-full max-w-page px-5 py-8">
      <h1 className="text-xl font-semibold tracking-tightest text-fg">Regression scorecard</h1>
      <p className="mt-1 text-sm text-fg-muted">
        {data ? `Last run ${formatTimestamp(data.generated_at)} · ${(data.total_ms / 1000).toFixed(1)}s total runtime` : 'Last run —'}
      </p>

      {error &&
      <p className="mt-6 rounded-md border border-danger-line bg-danger-soft px-4 py-3 text-sm text-danger">
          {error}
        </p>
      }

      {!data && !error &&
      <div className="mt-6 space-y-3" role="status" aria-live="polite">
          <span className="sr-only">Loading scorecard</span>
          <Skeleton className="h-20 w-full rounded-md" />
          <Skeleton className="h-64 w-full rounded-md" />
        </div>
      }

      {data &&
      <>
          <dl className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-md border border-line bg-surface px-4 py-3">
              <dt className="text-2xs uppercase tracking-label text-fg-faint">Questions passed</dt>
              <dd className="mt-1 font-mono text-lg text-fg">
                {questionsPassed} / {questionsTotal}
              </dd>
            </div>
            <div className="rounded-md border border-line bg-surface px-4 py-3">
              <dt className="text-2xs uppercase tracking-label text-fg-faint">Scenarios passed</dt>
              <dd className="mt-1 font-mono text-lg text-fg">
                {data.scenarios.passed} / {data.scenarios.total}
              </dd>
            </div>
            {data.tiers.map((tier) =>
          <div key={tier.tier} className="rounded-md border border-line bg-surface px-4 py-3">
                <dt className="text-2xs uppercase tracking-label text-fg-faint">Tier {tier.tier}</dt>
                <dd className="mt-1 font-mono text-lg text-fg">
                  {tier.passed} / {tier.total}
                </dd>
              </div>
          )}
          </dl>

          <div className="mt-6 overflow-x-auto rounded-md border border-line">
            <table className="w-full border-collapse text-left text-sm">
              <caption className="sr-only">Per-case regression results</caption>
              <thead>
                <tr className="bg-sunken">
                  <th scope="col" className="px-4 py-3 text-2xs font-semibold uppercase tracking-label text-fg-faint">
                    Case
                  </th>
                  <th scope="col" className="px-4 py-3 text-2xs font-semibold uppercase tracking-label text-fg-faint">
                    Tier
                  </th>
                  <th scope="col" className="px-4 py-3 text-2xs font-semibold uppercase tracking-label text-fg-faint">
                    Question
                  </th>
                  <th scope="col" className="px-4 py-3 text-2xs font-semibold uppercase tracking-label text-fg-faint">
                    Result
                  </th>
                  <th scope="col" className="px-4 py-3 text-2xs font-semibold uppercase tracking-label text-fg-faint">
                    Detail
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.cases.map((item) =>
              <tr key={item.id} className="border-t border-line">
                    <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-fg">{item.id}</td>
                    <td className="px-4 py-3 font-mono text-xs text-fg-muted">{item.tier}</td>
                    <td className="px-4 py-3 text-fg-muted">{item.question}</td>
                    <td
                  className={`whitespace-nowrap px-4 py-3 text-xs font-semibold ${
                  item.passed ? 'text-pass' : 'text-danger'}`
                  }>
                  
                      {item.passed ? 'Pass' : 'Fail'}
                    </td>
                    <td className="px-4 py-3 text-xs text-fg-faint">{item.detail}</td>
                  </tr>
              )}
              </tbody>
            </table>
          </div>
        </>
      }
    </main>);

}