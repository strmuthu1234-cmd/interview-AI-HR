import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api, errorMessage } from '../../api/client';
import { Alert, Badge, Card, Empty, Field, Modal, PageHeader, Spinner, TagInput } from '../../components/ui';
import { results, useFetch } from '../../hooks/useFetch';
import { fmtDate } from '../../lib/format';

export const EMPTY_JOB = {
  title: '', department: '', description: '', required_skills: [], preferred_skills: [], min_experience_years: 0, max_experience_years: '',
  responsibilities: '', mandatory_qualifications: [], shortlist_size: 10, interview_duration_minutes: 45, interview_language: 'en',
};

export function JobForm({ initial = EMPTY_JOB, onSaved, onCancel }) {
  const [f, setF] = useState({ ...EMPTY_JOB, ...initial, max_experience_years: initial.max_experience_years ?? '' });
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    const body = { ...f, max_experience_years: f.max_experience_years === '' ? null : Number(f.max_experience_years), min_experience_years: Number(f.min_experience_years), shortlist_size: Number(f.shortlist_size), interview_duration_minutes: Number(f.interview_duration_minutes) };
    try {
      const r = f.id ? await api.patch(`/jobs/${f.id}/`, body) : await api.post('/jobs/', body);
      onSaved(r.data);
    } catch (ex) { setErr(ex.response?.data && typeof ex.response.data === 'object' ? ex.response.data : { detail: errorMessage(ex) }); }
    finally { setBusy(false); }
  };
  const e = (k) => (err?.[k] ? [].concat(err[k]).join(' ') : undefined);

  return (
    <form onSubmit={submit} className="space-y-4">
      {err?.detail && <Alert>{err.detail}</Alert>}
      {err?.non_field_errors && <Alert>{err.non_field_errors.join(' ')}</Alert>}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Job title" error={e('title')}>{(id) => <input id={id} className="input" required value={f.title} onChange={set('title')} placeholder="Python Full Stack Developer" />}</Field>
        <Field label="Department" error={e('department')}>{(id) => <input id={id} className="input" value={f.department} onChange={set('department')} />}</Field>
      </div>
      <Field label="Job description" error={e('description')}>{(id) => <textarea id={id} className="input min-h-[90px]" required value={f.description} onChange={set('description')} />}</Field>
      <Field label="Required technical skills" hint="Each is matched literally against resumes (aliases like DRF / Postgres are understood)." error={e('required_skills')}>
        {() => <TagInput value={f.required_skills} onChange={(v) => setF({ ...f, required_skills: v })} />}
      </Field>
      <Field label="Preferred skills" error={e('preferred_skills')}>{() => <TagInput value={f.preferred_skills} onChange={(v) => setF({ ...f, preferred_skills: v })} />}</Field>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Min. experience (yrs)" error={e('min_experience_years')}>{(id) => <input id={id} type="number" min="0" step="0.5" className="input" value={f.min_experience_years} onChange={set('min_experience_years')} />}</Field>
        <Field label="Max. experience (yrs)" error={e('max_experience_years')} hint="Optional">{(id) => <input id={id} type="number" min="0" step="0.5" className="input" value={f.max_experience_years} onChange={set('max_experience_years')} />}</Field>
        <Field label="Shortlist slots" error={e('shortlist_size')}>{(id) => <input id={id} type="number" min="1" max="50" className="input" value={f.shortlist_size} onChange={set('shortlist_size')} />}</Field>
      </div>
      <Field label="Key responsibilities" error={e('responsibilities')}>{(id) => <textarea id={id} className="input min-h-[70px]" value={f.responsibilities} onChange={set('responsibilities')} />}</Field>
      <Field label="Mandatory qualifications" hint="e.g. Bachelor's degree in Computer Science or a related field" error={e('mandatory_qualifications')}>
        {() => <TagInput value={f.mandatory_qualifications} onChange={(v) => setF({ ...f, mandatory_qualifications: v })} />}
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Interview duration (minutes)" error={e('interview_duration_minutes')}>{(id) => <input id={id} type="number" min="5" className="input" value={f.interview_duration_minutes} onChange={set('interview_duration_minutes')} />}</Field>
        <Field label="Interview language" error={e('interview_language')}>{(id) => <select id={id} className="input" value={f.interview_language} onChange={set('interview_language')}><option value="en">English</option><option value="ta">Tamil (optional)</option></select>}</Field>
      </div>
      <div className="flex justify-end gap-2 pt-2">
        <button type="button" className="btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="btn-primary" disabled={busy}>{busy ? 'Saving…' : f.id ? 'Save changes' : 'Create job'}</button>
      </div>
    </form>
  );
}

export default function Jobs() {
  const { data, loading, error, reload } = useFetch('/jobs/', { params: { page_size: 100 } });
  const [open, setOpen] = useState(false);
  const jobs = results(data);
  return (
    <>
      <PageHeader title="Jobs" subtitle="Define what you are hiring for. Screening and interview scoring are always based on these requirements."
        actions={<button className="btn-primary" onClick={() => setOpen(true)}>+ New job</button>} />
      {loading ? <Spinner /> : error ? <Alert>{error}</Alert> : !jobs.length ? <Empty title="No jobs yet">Create your first job opening to start screening resumes.</Empty> : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {jobs.map((j) => (
            <Link key={j.id} to={`/jobs/${j.id}`} className="card block p-5 transition hover:-translate-y-0.5 hover:border-brand-200">
              <div className="flex items-start justify-between gap-2"><h3 className="font-semibold text-ink-900">{j.title}</h3><Badge tone={j.status === 'open' ? 'green' : 'gray'}>{j.status}</Badge></div>
              <p className="mt-0.5 text-xs text-ink-500">{j.department || 'No department'} · created {fmtDate(j.created_at)}</p>
              <div className="mt-3 flex flex-wrap gap-1.5">{j.required_skills.slice(0, 6).map((s) => <Badge key={s} tone="purple">{s}</Badge>)}{j.required_skills.length > 6 && <Badge>+{j.required_skills.length - 6}</Badge>}</div>
              <div className="mt-4 flex gap-6 text-sm text-ink-600"><span><b className="text-ink-900">{j.candidate_count}</b> candidates</span><span>{j.min_experience_years}{j.max_experience_years ? `–${j.max_experience_years}` : '+'} yrs</span><span>{j.shortlist_size} slots</span></div>
            </Link>
          ))}
        </div>
      )}
      <Modal open={open} onClose={() => setOpen(false)} title="New job opening" wide>
        <JobForm onCancel={() => setOpen(false)} onSaved={() => { setOpen(false); reload(); }} />
      </Modal>
    </>
  );
}
