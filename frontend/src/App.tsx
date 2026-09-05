import React from 'react';
import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom';
import { ThemeToggle } from './components/common/ThemeToggle';
import { ConsolePage } from './pages/ConsolePage';
import { ConnectPage } from './pages/ConnectPage';
import { ScorecardPage } from './pages/ScorecardPage';

const SNAPSHOT_LABEL = '14 Sep 2026 · 18:00Z · BLR';

function TopBar() {
  const linkClass = ({ isActive }: {isActive: boolean;}) =>
  `rounded-full px-4 py-1.5 text-xs transition-colors duration-150 ease-out ${
  isActive ? 'bg-accent text-accent-ink font-semibold' : 'text-fg-muted hover:text-fg'}`;


  return (
    <header className="shrink-0 border-b border-line bg-void">
      <div className="mx-auto flex w-full max-w-page flex-wrap items-center gap-4 px-5 py-3">
        <div className="flex items-baseline gap-2">
          <span className="text-base font-semibold tracking-tightest text-fg">
            d<span className="text-accent">C</span>ortex
          </span>
          <span className="text-xs text-fg-muted">Crew Ops Advisor</span>
        </div>
        <span className="hidden font-mono text-2xs text-fg-faint sm:inline">{SNAPSHOT_LABEL}</span>
        <nav aria-label="Sections" className="ml-auto flex items-center gap-1">
          <NavLink to="/" end className={linkClass}>
            Console
          </NavLink>
          <NavLink to="/scorecard" className={linkClass}>
            Scorecard
          </NavLink>
          <NavLink to="/connect" className={linkClass}>
            Connect
          </NavLink>
          <span aria-hidden="true" className="mx-1 h-4 w-px bg-line" />
          <ThemeToggle />
        </nav>
      </div>
    </header>);

}

export function App() {
  return (
    <BrowserRouter>
      {/* Fixed viewport height from lg up, so the header and the ask bar stay put and
          only the conversation scrolls. Below lg the page scrolls normally, which is the
          right behaviour on a phone. */}
      <div className="flex min-h-full w-full flex-col bg-void lg:h-screen lg:overflow-hidden">
        <TopBar />
        <div className="flex-1 lg:min-h-0">
          <Routes>
            <Route path="/" element={<ConsolePage />} />
            <Route path="/scorecard" element={<ScorecardPage />} />
            <Route path="/connect" element={<ConnectPage />} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>);

}