import { useCallback, useRef, useState } from 'react';
import { askAdvisor, simulate } from '../services/api';
import type { AdvisorResponse, SimulateRequest } from '../types/api';

export interface Exchange {
  id: string;
  question: string;
  kind: 'question' | 'what_if';
  response: AdvisorResponse | null;
  error: string | null;
}

function newId(): string {
  return `x-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

/** Owns the conversation thread. Session id carries multi-turn context to the backend. */
export function useAdvisor() {
  const [thread, setThread] = useState<Exchange[]>([]);
  const [pending, setPending] = useState(false);
  const sessionId = useRef<string>(`s-${Math.random().toString(36).slice(2, 10)}`);

  const run = useCallback(
    async (question: string, kind: Exchange['kind'], call: () => Promise<AdvisorResponse>) => {
      const id = newId();
      setThread((prev) => [...prev, { id, question, kind, response: null, error: null }]);
      setPending(true);
      try {
        const response = await call();
        setThread((prev) => prev.map((item) => item.id === id ? { ...item, response } : item));
      } catch {
        setThread((prev) =>
        prev.map((item) =>
        item.id === id ?
        { ...item, error: 'The advisor service did not respond. Nothing was changed.' } :
        item
        )
        );
      } finally {
        setPending(false);
      }
    },
    []
  );

  const ask = useCallback(
    (question: string) => run(question, 'question', () => askAdvisor(question, sessionId.current)),
    [run]
  );

  const runWhatIf = useCallback(
    (question: string) => {
      const body: SimulateRequest = { question, session_id: sessionId.current };
      return run(question, 'what_if', () => simulate(body));
    },
    [run]
  );

  return { thread, pending, ask, runWhatIf };
}