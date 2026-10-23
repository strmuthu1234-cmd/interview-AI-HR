import { useEffect, useId, useRef, useState } from 'react';
import { bandTone, fmtScore, scoreTone, STATUS_LABEL } from '../lib/format';

const TONES = {
  gray: 'bg-gray-100 text-ink-600',
  purple: 'bg-brand-100 text-brand-800',
  green: 'bg-emerald-100 text-emerald-800',
  amber: 'bg-amber-100 text-amber-800',
  red: 'bg-red-100 text-red-800',
  blue: 'bg-sky-100 text-sky-800',
};

export function Badge({ tone = 'gray', children, className = '' }) {
  return <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold ${TONES[tone]} ${className}`}>{children}</span>;
}

const STATUS_TONE = {
  selected: 'green', rejected: 'red', on_hold: 'amber', completed: 'green', interviewed: 'blue', in_progress: 'blue', interviewing: 'blue',
  generation_failed: 'red', generating_questions: 'amber', draft: 'amber', ready: 'purple', interview_invited: 'purple', shortlisted: 'purple',
};
export const StatusBadge = ({ status }) => <Badge tone={STATUS_TONE[status] || 'gray'}>{STATUS_LABEL[status] || status}</Badge>;

export const ScoreBadge = ({ value, suffix = '' }) => <Badge tone={scoreTone(value)}>{fmtScore(value)}{value != null && suffix}</Badge>;
export const BandBadge = ({ band }) => (band ? <Badge tone={bandTone(band)}>{band}</Badge> : null);

export function Card({ title, action, children, className = '', pad = true }) {
  return (
    <section className={`card ${className}`}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 border-b border-gray-100 px-5 py-3.5">
          <h2 className="text-sm font-semibold text-ink-900">{title}</h2>
          {action}
        </header>
      )}
      <div className={pad ? 'p-5' : ''}>{children}</div>
    </section>
  );
}

export function Stat({ label, value, hint, accent }) {
  return (
    <div className="card p-5">
      <p className="text-xs font-semibold uppercase tracking-wide text-ink-500">{label}</p>
      <p className={`mt-2 text-3xl font-bold ${accent ? 'text-brand-700' : 'text-ink-900'}`}>{value ?? '—'}</p>
      {hint && <p className="mt-1 text-xs text-ink-500">{hint}</p>}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-ink-900">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-sm text-ink-500">{subtitle}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">{actions}</div>
    </div>
  );
}

export function Spinner({ label = 'Loading…' }) {
  return (
    <div role="status" className="flex items-center justify-center gap-3 py-10 text-sm text-ink-500">
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-brand-200 border-t-brand-700" />
      {label}
    </div>
  );
}

export function Empty({ title, children }) {
  return (
    <div className="rounded-2xl border border-dashed border-gray-200 px-6 py-10 text-center">
      <p className="font-semibold text-ink-800">{title}</p>
      {children && <div className="mt-1 text-sm text-ink-500">{children}</div>}
    </div>
  );
}

export function Alert({ tone = 'red', title, children, className = '' }) {
  const t = { red: 'border-red-200 bg-red-50 text-red-800', amber: 'border-amber-200 bg-amber-50 text-amber-900', blue: 'border-sky-200 bg-sky-50 text-sky-900', green: 'border-emerald-200 bg-emerald-50 text-emerald-900', purple: 'border-brand-200 bg-brand-50 text-brand-900' }[tone];
  return (
    <div role={tone === 'red' ? 'alert' : 'status'} className={`rounded-xl border px-4 py-3 text-sm ${t} ${className}`}>
      {title && <p className="font-semibold">{title}</p>}
      {children && <div className={title ? 'mt-0.5' : ''}>{children}</div>}
    </div>
  );
}

export function Field({ label, hint, error, children }) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="label">{label}</label>
      {typeof children === 'function' ? children(id) : children}
      {hint && !error && <p className="mt-1 text-xs text-ink-500">{hint}</p>}
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  );
}

export function Modal({ open, onClose, title, children, wide = false }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    ref.current?.focus();
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink-900/40 p-4 backdrop-blur-sm sm:p-10" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title} className={`card w-full ${wide ? 'max-w-3xl' : 'max-w-lg'} outline-none`}>
        <header className="flex items-center justify-between border-b border-gray-100 px-5 py-3.5">
          <h2 className="font-semibold text-ink-900">{title}</h2>
          <button className="btn-ghost !px-2 !py-1" onClick={onClose} aria-label="Close dialog">✕</button>
        </header>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export function ProgressBar({ value, max = 100, tone = 'brand', label }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div role="progressbar" aria-valuenow={Math.round(value)} aria-valuemin={0} aria-valuemax={max} aria-label={label} className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
      <div className={`h-full rounded-full transition-all duration-500 ${tone === 'green' ? 'bg-emerald-500' : 'bg-brand-600'}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function ScoreBar({ label, value, weight, note }) {
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between text-sm">
        <span className="font-medium text-ink-800">{label}{weight != null && <span className="ml-2 text-xs font-normal text-ink-500">weight {weight}%</span>}</span>
        <span className="font-semibold text-ink-900">{value == null ? 'n/a' : fmtScore(value)}</span>
      </div>
      <ProgressBar value={value ?? 0} label={label} />
      {note && <p className="mt-1 text-xs text-ink-500">{note}</p>}
    </div>
  );
}

export function Tabs({ tabs, active, onChange }) {
  return (
    <div role="tablist" className="mb-5 flex gap-1 overflow-x-auto border-b border-gray-200">
      {tabs.map((t) => (
        <button key={t.id} role="tab" aria-selected={active === t.id} onClick={() => onChange(t.id)}
          className={`whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-semibold transition ${active === t.id ? 'border-brand-700 text-brand-700' : 'border-transparent text-ink-500 hover:text-ink-800'}`}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Table({ columns, rows, rowKey, onRowClick, empty }) {
  if (!rows?.length) return empty || null;
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-100">
        <thead className="bg-gray-50/70"><tr>{columns.map((c) => <th key={c.key} className={`th ${c.className || ''}`}>{c.header}</th>)}</tr></thead>
        <tbody className="divide-y divide-gray-100">
          {rows.map((r) => (
            <tr key={rowKey(r)} onClick={onRowClick ? () => onRowClick(r) : undefined} className={onRowClick ? 'cursor-pointer hover:bg-brand-50/50' : ''}>
              {columns.map((c) => <td key={c.key} className={`td ${c.className || ''}`}>{c.render ? c.render(r) : r[c.key]}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function TagInput({ value, onChange, placeholder = 'Type and press Enter' }) {
  const [text, setText] = useState('');
  const add = () => {
    const v = text.trim().replace(/,$/, '');
    if (v && !value.some((x) => x.toLowerCase() === v.toLowerCase())) onChange([...value, v]);
    setText('');
  };
  return (
    <div className="flex min-h-[42px] flex-wrap items-center gap-1.5 rounded-xl border border-gray-200 bg-white px-2 py-1.5 focus-within:border-brand-500 focus-within:ring-2 focus-within:ring-brand-200">
      {value.map((t) => (
        <span key={t} className="inline-flex items-center gap-1 rounded-lg bg-brand-50 px-2 py-1 text-xs font-semibold text-brand-800">
          {t}
          <button type="button" aria-label={`Remove ${t}`} className="text-brand-500 hover:text-brand-900" onClick={() => onChange(value.filter((x) => x !== t))}>×</button>
        </span>
      ))}
      <input className="min-w-[8rem] flex-1 bg-transparent px-1 py-1 text-sm outline-none" value={text} placeholder={value.length ? '' : placeholder}
        onChange={(e) => setText(e.target.value)} onBlur={add}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); add(); } else if (e.key === 'Backspace' && !text && value.length) onChange(value.slice(0, -1)); }} />
    </div>
  );
}

export function CopyButton({ text, label = 'Copy' }) {
  const [done, setDone] = useState(false);
  return (
    <button type="button" className="btn-secondary" onClick={async () => { try { await navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1500); } catch { window.prompt('Copy this link:', text); } }}>
      {done ? 'Copied ✓' : label}
    </button>
  );
}
