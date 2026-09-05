import React from 'react';
import { FlaskConicalIcon } from 'lucide-react';
import type { AdvisorResponse } from '../../types/api';

type Row = NonNullable<AdvisorResponse['before_after']>[number];

export function BeforeAfterDiff({ rows }: {rows: Row[];}) {
  return (
    <section aria-label="Simulated before and after">
      <div className="mb-3 flex items-center gap-2 rounded-md border border-info-line bg-info-soft px-4 py-2.5">
        <FlaskConicalIcon aria-hidden="true" className="h-4 w-4 shrink-0 text-info" />
        <p className="text-xs text-info">
          Simulation only. The roster, the pairings and the flights are unchanged.
        </p>
      </div>

      <div className="overflow-x-auto rounded-md border border-line">
        <table className="w-full border-collapse text-left text-sm">
          <caption className="sr-only">Duty, flight hours, rest and legality before and after</caption>
          <thead>
            <tr className="bg-sunken">
              <th scope="col" className="px-4 py-2 text-2xs font-semibold uppercase tracking-label text-fg-faint">
                Field
              </th>
              <th scope="col" className="px-4 py-2 text-2xs font-semibold uppercase tracking-label text-fg-faint">
                Now
              </th>
              <th scope="col" className="px-4 py-2 text-2xs font-semibold uppercase tracking-label text-fg-faint">
                If applied
              </th>
              <th scope="col" className="px-4 py-2 text-2xs font-semibold uppercase tracking-label text-fg-faint">
                Change
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) =>
            <tr key={row.field} className="border-t border-line">
                <th scope="row" className="px-4 py-3 text-left text-sm font-normal text-fg-muted">
                  {row.field}
                </th>
                <td className="px-4 py-3 font-mono text-xs text-fg-muted">{row.before}</td>
                <td
                className={`px-4 py-3 font-mono text-xs ${row.legal ? 'text-fg' : 'text-danger'}`}>
                
                  {row.after}
                  {!row.legal &&
                <span className="ml-2 rounded-full border border-danger-line bg-danger-soft px-2 py-0.5 text-2xs">
                      breach
                    </span>
                }
                </td>
                <td className="px-4 py-3 font-mono text-xs text-fg-faint">{row.delta}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>);

}