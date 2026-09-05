import React from 'react';

interface ResultTableProps {
  columns: string[];
  rows: (string | number)[][];
  caption?: string;
}

export function ResultTable({ columns, rows, caption }: ResultTableProps) {
  return (
    <div className="overflow-x-auto rounded-md border border-line">
      <table className="w-full border-collapse text-left text-sm">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr className="bg-sunken">
            {columns.map((column) =>
            <th
              key={column}
              scope="col"
              className="whitespace-nowrap px-4 py-3 text-2xs font-semibold uppercase tracking-label text-fg-faint">
              
                {column}
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) =>
          <tr key={rowIndex} className="border-t border-line">
              {row.map((cell, cellIndex) =>
            <td
              key={cellIndex}
              className={`px-4 py-3 align-top ${
              cellIndex === 0 ? 'font-mono text-fg' : 'text-fg-muted'}`
              }>
              
                  {cell}
                </td>
            )}
            </tr>
          )}
        </tbody>
      </table>
    </div>);

}