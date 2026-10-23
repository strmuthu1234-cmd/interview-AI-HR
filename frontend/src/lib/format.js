export const fmtScore = (v, digits = 1) => (v === null || v === undefined ? '—' : Number(v).toFixed(digits).replace(/\.0+$/, ''));

export const fmtDate = (d) => (d ? new Date(d).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—');

export const fmtDuration = (s) => {
  if (!s && s !== 0) return '—';
  const m = Math.floor(s / 60);
  return m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m}m ${s % 60}s`;
};

export const fmtClock = (s) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

export const STATUS_LABEL = {
  new: 'New', screened: 'Screened', shortlisted: 'Shortlisted', interview_invited: 'Invited', interviewing: 'Interviewing',
  interviewed: 'Interviewed', selected: 'Selected', rejected: 'Rejected', on_hold: 'On hold',
  generating_questions: 'Generating questions', generation_failed: 'Generation failed', draft: 'Review questions', ready: 'Ready to invite',
  in_progress: 'In progress', completed: 'Completed', expired: 'Expired',
};

export const bandTone = (band) => (!band ? 'gray' : /strong/i.test(band) ? 'green' : /good/i.test(band) ? 'purple' : /review/i.test(band) ? 'amber' : 'red');

export const scoreTone = (v) => (v === null || v === undefined ? 'gray' : v >= 85 ? 'green' : v >= 70 ? 'purple' : v >= 50 ? 'amber' : 'red');

export const download = (blob, filename) => {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};

export const newId = () => (crypto?.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`);

export const safeStorage = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* ignore */ } },
  remove(k) { try { localStorage.removeItem(k); } catch { /* ignore */ } },
};
