import { useCallback, useEffect, useState } from 'react';

/** What the controller chose. "system" follows the OS setting as it changes. */
export type ThemePreference = 'system' | 'light' | 'dark';
/** What is actually painted. */
export type ResolvedTheme = 'light' | 'dark';

const STORAGE_KEY = 'crew-ops-theme';
const ORDER: ThemePreference[] = ['system', 'light', 'dark'];

function systemTheme(): ResolvedTheme {
  if (typeof window === 'undefined' || !window.matchMedia) return 'dark';
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

function readStored(): ThemePreference {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === 'light' || raw === 'dark' || raw === 'system') return raw;
  } catch {
    // private windows and blocked site data both throw here; the default is fine
  }
  return 'system';
}

export function resolve(preference: ThemePreference): ResolvedTheme {
  return preference === 'system' ? systemTheme() : preference;
}

/** Paint the theme. Kept outside React so the pre-paint script can share the rule. */
export function applyTheme(resolved: ResolvedTheme, animate = true): void {
  const root = document.documentElement;
  if (animate) {
    root.classList.add('theme-transition');
    window.setTimeout(() => root.classList.remove('theme-transition'), 260);
  }
  root.setAttribute('data-theme', resolved);
}

export function useTheme() {
  const [preference, setPreference] = useState<ThemePreference>(readStored);
  const [resolved, setResolved] = useState<ResolvedTheme>(() => resolve(readStored()));

  useEffect(() => {
    const next = resolve(preference);
    setResolved(next);
    applyTheme(next);
    try {
      localStorage.setItem(STORAGE_KEY, preference);
    } catch {
      // choice simply will not persist; the session still honours it
    }
  }, [preference]);

  // follow the OS while the preference is "system"
  useEffect(() => {
    if (preference !== 'system' || !window.matchMedia) return;
    const query = window.matchMedia('(prefers-color-scheme: light)');
    const onChange = () => {
      const next = systemTheme();
      setResolved(next);
      applyTheme(next);
    };
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, [preference]);

  const cycle = useCallback(() => {
    setPreference((current) => ORDER[(ORDER.indexOf(current) + 1) % ORDER.length]);
  }, []);

  return { preference, resolved, setPreference, cycle };
}
