import React from 'react';
import type { RuleCheck } from '../../types/api';

const statusStyle: Record<RuleCheck['status'], string> = {
  PASS: 'text-pass',
  FAIL: 'text-danger',
  NOT_APPLICABLE: 'text-fg-faint'
};

const statusLabel: Record<RuleCheck['status'], string> = {
  PASS: 'Pass',
  FAIL: 'Fail',
  NOT_APPLICABLE: 'N/A'
};

function marginLabel(margin: number | null): string {
  if (margin === null) return '—';
  const value = Math.abs(margin);
  return margin < 0 ? `${value} over` : `${value} spare`;
}

export function RuleCheckList({ checks }: {checks: RuleCheck[];}) {
  return (
    <div className="overflow-x-auto rounded-md border border-line">
      <table className="w-full border-collapse text-left text-sm">
        <caption className="sr-only">Rule checks for this option</caption>
        <thead>
          <tr className="bg-sunken">
            <th scope="col" className="px-4 py-2 text-2xs font-semibold uppercase tracking-label text-fg-faint">
              Rule
            </th>
            <th scope="col" className="px-4 py-2 text-2xs font-semibold uppercase tracking-label text-fg-faint">
              Result
            </th>
            <th scope="col" className="px-4 py-2 text-2xs font-semibold uppercase tracking-label text-fg-faint">
              Actual
            </th>
            <th scope="col" className="px-4 py-2 text-2xs font-semibold uppercase tracking-label text-fg-faint">
              Limit
            </th>
            <th scope="col" className="px-4 py-2 text-2xs font-semibold uppercase tracking-label text-fg-faint">
              Margin
            </th>
          </tr>
        </thead>
        <tbody>
          {checks.map((check) =>
          <React.Fragment key={check.rule_id}>
              <tr className="border-t border-line">
                <td className="whitespace-nowrap px-4 py-2 font-mono text-xs text-fg">{check.rule_id}</td>
                <td className={`whitespace-nowrap px-4 py-2 text-xs font-semibold ${statusStyle[check.status]}`}>
                  {statusLabel[check.status]}
                </td>
                <td className="whitespace-nowrap px-4 py-2 font-mono text-xs text-fg-muted">
                  {check.actual ?? '—'}
                </td>
                <td className="whitespace-nowrap px-4 py-2 font-mono text-xs text-fg-muted">
                  {check.limit ?? '—'}
                </td>
                <td
                className={`whitespace-nowrap px-4 py-2 font-mono text-xs ${
                check.margin !== null && check.margin < 0 ? 'text-danger' : 'text-fg-muted'}`
                }>
                
                  {marginLabel(check.margin)}
                </td>
              </tr>
              <tr className="border-t border-line">
                <td colSpan={5} className="px-4 pb-3 pt-0 text-xs leading-relaxed text-fg-faint">
                  {check.detail}
                </td>
              </tr>
            </React.Fragment>
          )}
        </tbody>
      </table>
    </div>);

}