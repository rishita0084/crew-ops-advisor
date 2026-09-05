import { MonitorIcon, MoonIcon, SunIcon } from 'lucide-react';
import { useTheme, type ThemePreference } from '../../hooks/useTheme';

const OPTIONS: {
  value: ThemePreference;
  label: string;
  Icon: typeof SunIcon;
}[] = [
  { value: 'system', label: 'Match system', Icon: MonitorIcon },
  { value: 'light', label: 'Light', Icon: SunIcon },
  { value: 'dark', label: 'Dark', Icon: MoonIcon }];


/**
 * Three explicit states rather than a two-way switch: "system" is a real choice,
 * and a controller who has their machine on a schedule should not have to fight it.
 */
export function ThemeToggle() {
  const { preference, resolved, setPreference } = useTheme();

  return (
    <div
      role="radiogroup"
      aria-label="Colour theme"
      className="flex items-center gap-0.5 rounded-full border border-line bg-surface p-0.5">

      {OPTIONS.map(({ value, label, Icon }) => {
        const active = preference === value;
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={
            value === 'system' ? `${label} (currently ${resolved})` : label
            }
            title={value === 'system' ? `${label} — currently ${resolved}` : label}
            onClick={() => setPreference(value)}
            className={`flex h-6 w-6 items-center justify-center rounded-full transition-colors duration-150 ease-out ${
            active ?
            'bg-accent text-accent-ink' :
            'text-fg-faint hover:text-fg'}`
            }>

            <Icon aria-hidden="true" className="h-3.5 w-3.5" />
          </button>);

      })}
    </div>);

}
