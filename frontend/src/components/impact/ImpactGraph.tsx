import React from 'react';
import type { ImpactReport } from '../../types/api';

type Node = ImpactReport['graph']['nodes'][number];

const statusStyle: Record<Node['status'], string> = {
  ok: 'border-line bg-raised text-fg-muted',
  at_risk: 'border-warning-line bg-warning-soft text-warning',
  broken: 'border-danger-line bg-danger-soft text-danger'
};

const statusLabel: Record<Node['status'], string> = {
  ok: 'Unaffected',
  at_risk: 'At risk',
  broken: 'Broken'
};

function NodeBox({ node }: {node: Node;}) {
  return (
    <div className={`rounded-md border px-4 py-3 text-center ${statusStyle[node.status]}`}>
      <p className="font-mono text-xs leading-snug">{node.label}</p>
      <p className="mt-1 text-2xs uppercase tracking-label opacity-80">{statusLabel[node.status]}</p>
    </div>);

}

function Connector({ count }: {count: number;}) {
  return (
    <div
      aria-hidden="true"
      className="grid"
      style={{ gridTemplateColumns: `repeat(${Math.max(count, 1)}, minmax(0, 1fr))` }}>
      
      {Array.from({ length: Math.max(count, 1) }).map((_, index) => {
        const busPosition =
        count === 1 ?
        'hidden' :
        index === 0 ?
        'left-1/2 right-0' :
        index === count - 1 ?
        'left-0 right-1/2' :
        'left-0 right-0';
        return (
          <div key={index} className="relative h-6">
            <span className={`absolute top-0 h-px bg-line-strong ${busPosition}`} />
            <span className="absolute left-1/2 top-0 h-6 w-px bg-line-strong" />
          </div>);

      })}
    </div>);

}

function Band({ label, nodes }: {label: string;nodes: Node[];}) {
  return (
    <div>
      <p className="mb-2 text-center text-2xs font-semibold uppercase tracking-label text-fg-faint">
        {label}
      </p>
      <div
        className="grid gap-3"
        style={{ gridTemplateColumns: `repeat(${Math.max(nodes.length, 1)}, minmax(0, 1fr))` }}>
        
        {nodes.map((node) =>
        <NodeBox key={node.id} node={node} />
        )}
      </div>
    </div>);

}

export function ImpactGraph({ impact }: {impact: ImpactReport;}) {
  const { nodes, edges } = impact.graph;
  const isTarget = (id: string) => edges.some((edge) => edge.to === id);

  const originCrew = nodes.filter((node) => node.type === 'crew' && !isTarget(node.id));
  const pairings = nodes.filter((node) => node.type === 'pairing');
  const flights = nodes.filter((node) => node.type === 'flight');
  const downstreamCrew = nodes.filter((node) => node.type === 'crew' && isTarget(node.id));

  const bands: {label: string;nodes: Node[];}[] = [
  { label: 'Crew', nodes: originCrew },
  { label: 'Pairing', nodes: pairings },
  { label: 'Flights', nodes: flights },
  { label: 'Downstream crew', nodes: downstreamCrew }].
  filter((band) => band.nodes.length > 0);

  return (
    <section aria-label="Cascade of the disruption">
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-md border border-line bg-sunken px-4 py-3">
          <p className="text-2xs uppercase tracking-label text-fg-faint">Uncrewed flights</p>
          <p className="mt-1 text-xl font-semibold text-danger">{impact.uncrewed_flights.length}</p>
          <p className="mt-1 font-mono text-xs text-fg-muted">{impact.uncrewed_flights.join(' · ')}</p>
        </div>
        <div className="rounded-md border border-line bg-sunken px-4 py-3">
          <p className="text-2xs uppercase tracking-label text-fg-faint">Passengers affected</p>
          <p className="mt-1 text-xl font-semibold text-fg">{impact.passengers_affected}</p>
          <p className="mt-1 text-xs text-fg-muted">Across the uncrewed legs</p>
        </div>
        <div className="rounded-md border border-line bg-sunken px-4 py-3">
          <p className="text-2xs uppercase tracking-label text-fg-faint">Pairings broken</p>
          <p className="mt-1 text-xl font-semibold text-fg">{impact.pairing_broken.length}</p>
          <p className="mt-1 font-mono text-xs text-fg-muted">{impact.pairing_broken.join(' · ')}</p>
        </div>
      </div>

      <div className="mt-5 overflow-x-auto rounded-md border border-line bg-sunken p-5">
        <div className="mx-auto min-w-[34rem] max-w-[38rem]">
          {bands.map((band, index) =>
          <div key={band.label}>
              {index > 0 && <Connector count={band.nodes.length} />}
              <Band label={band.label} nodes={band.nodes} />
            </div>
          )}
        </div>
      </div>

      <p className="mt-3 text-xs text-fg-muted">Trigger: {impact.trigger}</p>

      {impact.downstream_risks.length > 0 &&
      <div className="mt-5">
          <h4 className="text-2xs font-semibold uppercase tracking-label text-fg-faint">
            Downstream risk
          </h4>
          <ul className="mt-2 divide-y divide-line rounded-md border border-line">
            {impact.downstream_risks.map((risk, index) =>
          <li key={index} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-3">
                <span className="font-mono text-xs text-fg">{risk.crew_id}</span>
                <span className="font-mono text-2xs text-warning">{risk.rule}</span>
                <span className="w-full text-sm text-fg-muted sm:w-auto sm:flex-1">{risk.detail}</span>
              </li>
          )}
          </ul>
        </div>
      }
    </section>);

}