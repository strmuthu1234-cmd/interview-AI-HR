import { useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

const I = {
  dash: 'M3 12l9-9 9 9M5 10v10h5v-6h4v6h5V10',
  jobs: 'M4 7h16v12H4zM9 7V5a2 2 0 012-2h2a2 2 0 012 2v2',
  people: 'M17 20v-2a4 4 0 00-4-4H7a4 4 0 00-4 4v2M10 10a4 4 0 100-8 4 4 0 000 8zM21 20v-2a4 4 0 00-3-3.9',
  mic: 'M12 3a3 3 0 00-3 3v6a3 3 0 006 0V6a3 3 0 00-3-3zM5 11a7 7 0 0014 0M12 18v3',
  chart: 'M4 20V10M10 20V4M16 20v-7M22 20H2',
  gear: 'M12 15a3 3 0 100-6 3 3 0 000 6zM19 12a7 7 0 00-.1-1.2l2-1.5-2-3.4-2.3 1a7 7 0 00-2-1.2L14 3h-4l-.6 2.7a7 7 0 00-2 1.2l-2.3-1-2 3.4 2 1.5A7 7 0 005 12c0 .4 0 .8.1 1.2l-2 1.5 2 3.4 2.3-1a7 7 0 002 1.2L10 21h4l.6-2.7a7 7 0 002-1.2l2.3 1 2-3.4-2-1.5c.1-.4.1-.8.1-1.2z',
  shield: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z',
  log: 'M6 3h9l3 3v15H6zM9 11h6M9 15h6',
};

const Icon = ({ d }) => (
  <svg viewBox="0 0 24 24" className="h-5 w-5 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>
);

const NAV = [
  { to: '/', label: 'Dashboard', icon: I.dash, end: true },
  { to: '/jobs', label: 'Jobs & Screening', icon: I.jobs },
  { to: '/candidates', label: 'Candidates', icon: I.people },
  { to: '/interviews', label: 'Interviews', icon: I.mic },
  { to: '/reports', label: 'Reports', icon: I.chart },
  { to: '/settings', label: 'Settings', icon: I.gear },
];
const ADMIN_NAV = [
  { to: '/users', label: 'Users', icon: I.shield },
  { to: '/audit', label: 'Audit log', icon: I.log },
];

export default function Layout() {
  const { user, logout, isAdmin } = useAuth();
  const [open, setOpen] = useState(false);
  const link = ({ isActive }) => `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition ${isActive ? 'bg-brand-50 text-brand-800' : 'text-ink-600 hover:bg-gray-50 hover:text-ink-900'}`;
  return (
    <div className="min-h-screen bg-gray-50/60 lg:flex">
      <aside className={`fixed inset-y-0 left-0 z-40 w-64 transform border-r border-gray-100 bg-white p-4 transition-transform lg:static lg:translate-x-0 ${open ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="mb-6 flex items-center gap-3 px-2 pt-1">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-brand-700 text-sm font-bold text-white">HR</div>
          <div><p className="text-sm font-bold leading-tight text-ink-900">AI Recruitment</p><p className="text-xs text-ink-500">Interview System</p></div>
        </div>
        <nav className="space-y-1" aria-label="Main" onClick={() => setOpen(false)}>
          {NAV.map((n) => <NavLink key={n.to} to={n.to} end={n.end} className={link}><Icon d={n.icon} />{n.label}</NavLink>)}
          {isAdmin && <p className="px-3 pb-1 pt-4 text-xs font-semibold uppercase tracking-wide text-ink-400">Administration</p>}
          {isAdmin && ADMIN_NAV.map((n) => <NavLink key={n.to} to={n.to} className={link}><Icon d={n.icon} />{n.label}</NavLink>)}
        </nav>
        <p className="absolute inset-x-4 bottom-4 rounded-xl bg-brand-50 p-3 text-xs leading-relaxed text-brand-900">
          AI scores support your decision – they never select or reject candidates. Every outcome is recorded by an HR user.
        </p>
      </aside>
      {open && <button aria-label="Close menu" className="fixed inset-0 z-30 bg-ink-900/30 lg:hidden" onClick={() => setOpen(false)} />}
      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-20 flex items-center justify-between border-b border-gray-100 bg-white/90 px-4 py-3 backdrop-blur sm:px-8">
          <button className="btn-ghost lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu">☰</button>
          <div className="hidden lg:block" />
          <div className="flex items-center gap-3">
            <div className="text-right"><p className="text-sm font-semibold text-ink-900">{user.first_name || user.username}</p><p className="text-xs capitalize text-ink-500">{user.role.replace('_', ' ')}</p></div>
            <button className="btn-secondary" onClick={logout}>Sign out</button>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-8 sm:px-8"><Outlet /></main>
      </div>
    </div>
  );
}
