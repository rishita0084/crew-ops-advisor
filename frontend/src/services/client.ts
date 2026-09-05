// Transport layer only. No component imports this directly.

type Env = Record<string, string | undefined>;

const env: Env = typeof import.meta !== 'undefined' && (import.meta as unknown as {env?: Env;}).env || {};

export const BASE_URL = env.VITE_API_BASE_URL || 'http://localhost:8000';

// TODO: defaults to mocks so the console runs standalone; set VITE_USE_MOCKS=false to hit the live API.
export const USE_MOCKS = String(env.VITE_USE_MOCKS ?? 'true').toLowerCase() === 'true';

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    throw new ApiError('The advisor service could not be reached.', res.status);
  }
  return (await res.json()) as T;
}

export async function get<T>(path: string, params?: Record<string, string | undefined>): Promise<T> {
  const url = new URL(path, BASE_URL);
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value) url.searchParams.set(key, value);
  });
  const res = await fetch(url.toString(), { headers: { Accept: 'application/json' } });
  return handle<T>(res);
}

export async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(new URL(path, BASE_URL).toString(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body)
  });
  return handle<T>(res);
}

/** Keeps mock responses feeling like a real round-trip without blocking the UI. */
export function delay<T>(value: T, ms = 520): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}