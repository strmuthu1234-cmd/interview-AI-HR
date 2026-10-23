import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, errorMessage } from '../../api/client';
import { Alert, Badge, Card, Empty, Field, PageHeader, ScoreBar, ScoreBadge, Spinner, StatusBadge, Tabs, TagInput } from '../../components/ui';
import { useFetch } from '../../hooks/useFetch';
import { fmtDate } from '../../lib/format';

const CAT_LABEL = { required_skills: 'Required technical skills', experience: 'Relevant professional experience', projects: 'Project relevance', preferred_skills: 'Preferred skills', qualifications: 'Job-related qualifications' };

function Analysis({ a, c, reload }) {
  const [note, setNote] = useState(a?.hr_review_note || '');
  const [adj, setAdj] = useState(a?.hr_adjusted_score ?? '');
  const [msg, setMsg] = useState(null);
  if (!a) return <Empty title="No assessment yet">{c.parse_error || 'The resume has not been analysed.'}</Empty>;
  const dispute = async (e) => {
    e.preventDefault();
    try { await api.post(`/candidates/${c.id}/dispute/`, { note, adjusted_score: adj === '' ? null : Number(adj) }); setMsg({ tone: 'green', text: 'Review recorded. The ranking now uses your adjusted score.' }); reload(); }
    catch (ex) { setMsg({ tone: 'red', text: errorMessage(ex) }); }
  };
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="space-y-6 lg:col-span-2">
        <Card title="Job-fit assessment" action={<div className="flex items-center gap-2">{a.is_disputed && <Badge tone="amber">Reviewed by HR</Badge>}<Badge tone="gray">{a.method === 'ai_assisted' ? `AI-assisted (${a.provider})` : 'Rule-based · deterministic'}</Badge></div>}>
          <div className="mb-5 flex items-end gap-3"><span className="text-5xl font-bold text-brand-700">{Number(a.effective_score).toFixed(0)}</span><span className="pb-2 text-ink-500">/ 100 match score</span>
            {a.hr_adjusted_score != null && <span className="pb-2 text-xs text-ink-500">(AI score {Number(a.match_score).toFixed(0)}, adjusted by HR)</span>}</div>
          <p className="mb-5 text-sm text-ink-700">{a.summary}</p>
          <div className="space-y-4">
            {Object.entries(a.category_scores).map(([k, v]) => (
              <ScoreBar key={k} label={CAT_LABEL[k] || k} value={v.applicable ? v.score : null} weight={v.applicable ? v.effective_weight : v.weight}
                note={!v.applicable ? 'Not applicable for this job – weight redistributed' : k === 'experience' ? `${v.detail.relevant_years} relevant yrs vs ${v.detail.required_min_years}+ required – ${v.detail.status}` : undefined} />
            ))}
          </div>
        </Card>
        <Card title="Supporting evidence from the resume">
          {a.evidence.length ? <ul className="space-y-2 text-sm">{a.evidence.map((e, i) => (
            <li key={i} className="rounded-xl bg-gray-50 px-3 py-2"><div className="flex flex-wrap items-center gap-2"><Badge tone="purple">{CAT_LABEL[e.category] || e.category}</Badge><b>{e.claim}</b>{e.status === 'listed_only' && <Badge tone="amber">listed only</Badge>}</div>{e.snippet && <p className="mt-1 text-xs italic text-ink-600">“{e.snippet}”</p>}</li>
          ))}</ul> : <Empty title="No evidence found" />}
        </Card>
      </div>
      <div className="space-y-6">
        <Card title="Skills">
          <p className="label">Matching</p><div className="mb-4 flex flex-wrap gap-1.5">{a.matching_skills.length ? a.matching_skills.map((s) => <Badge key={s} tone="green">{s}</Badge>) : <span className="text-sm text-ink-500">None</span>}</div>
          <p className="label">Missing required</p><div className="flex flex-wrap gap-1.5">{a.missing_required_skills.length ? a.missing_required_skills.map((s) => <Badge key={s} tone="red">{s}</Badge>) : <span className="text-sm text-emerald-700">None</span>}</div>
        </Card>
        <Card title="Relevant projects">{a.relevant_projects.length ? a.relevant_projects.map((p) => <div key={p.name} className="mb-3 text-sm last:mb-0"><b>{p.name}</b> <Badge tone="purple">{p.relevance_pct}% of required</Badge><p className="text-xs text-ink-500">{p.matched_skills.join(', ')}</p></div>) : <p className="text-sm text-ink-500">None found.</p>}</Card>
        <Card title="Assessment limitations"><ul className="list-disc space-y-1 pl-5 text-xs text-ink-600">{a.limitations.map((l) => <li key={l}>{l}</li>)}</ul></Card>
        {c.resume.security_flags?.length > 0 && <Alert tone="red" title="Instruction-like text ignored">{c.resume.security_flags.map((f, i) => <p key={i} className="mt-1 break-words text-xs">“{f.line}”</p>)}</Alert>}
        <Card title="Dispute / adjust this assessment">
          <form onSubmit={dispute} className="space-y-3">
            <Field label="Reason (required)">{(id) => <textarea id={id} required minLength={5} className="input min-h-[70px]" value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
            <Field label="HR-adjusted score (optional)" hint="Leave empty to keep the AI score.">{(id) => <input id={id} type="number" min="0" max="100" step="0.5" className="input" value={adj} onChange={(e) => setAdj(e.target.value)} />}</Field>
            {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
            <button className="btn-secondary w-full">Record review</button>
          </form>
        </Card>
      </div>
    </div>
  );
}

function ProfileEditor({ c, reload }) {
  const p = c.profile || {};
  const [f, setF] = useState({ full_name: c.full_name, email: c.email, phone: c.phone, skills: p.skills || [], education: (p.education || []).join('\n'), certifications: (p.certifications || []).join('\n'), summary: p.summary || '', years: p.total_experience_years ?? 0 });
  const [msg, setMsg] = useState(null);
  const save = async (e) => {
    e.preventDefault();
    try {
      await api.patch(`/candidates/${c.id}/`, { full_name: f.full_name, email: f.email, phone: f.phone, reanalyze: true, profile: { skills: f.skills, summary: f.summary, education: f.education.split('\n').filter(Boolean), certifications: f.certifications.split('\n').filter(Boolean), total_experience_years: Number(f.years) } }, {});
      setMsg({ tone: 'green', text: 'Corrections saved and the assessment was recalculated. The original parsed data is kept for audit.' }); reload();
    } catch (ex) { setMsg({ tone: 'red', text: errorMessage(ex) }); }
  };
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title="Extracted information (editable)">
        <form onSubmit={save} className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Name">{(id) => <input id={id} className="input" value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} />}</Field>
            <Field label="Email">{(id) => <input id={id} className="input" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />}</Field>
            <Field label="Phone">{(id) => <input id={id} className="input" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} />}</Field>
            <Field label="Total experience (yrs)" hint={`Source: ${(p.experience_years_source || 'none').replace('_', ' ')}`}>{(id) => <input id={id} type="number" step="0.1" min="0" className="input" value={f.years} onChange={(e) => setF({ ...f, years: e.target.value })} />}</Field>
          </div>
          <Field label="Skills">{() => <TagInput value={f.skills} onChange={(v) => setF({ ...f, skills: v })} />}</Field>
          <Field label="Professional summary">{(id) => <textarea id={id} className="input min-h-[70px]" value={f.summary} onChange={(e) => setF({ ...f, summary: e.target.value })} />}</Field>
          <Field label="Education (one per line)">{(id) => <textarea id={id} className="input min-h-[60px]" value={f.education} onChange={(e) => setF({ ...f, education: e.target.value })} />}</Field>
          <Field label="Certifications (one per line)">{(id) => <textarea id={id} className="input min-h-[60px]" value={f.certifications} onChange={(e) => setF({ ...f, certifications: e.target.value })} />}</Field>
          {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
          <button className="btn-primary">Save corrections &amp; re-score</button>
        </form>
      </Card>
      <div className="space-y-6">
        <Card title="Work experience">{(p.experience || []).length ? p.experience.map((e, i) => <div key={i} className="mb-4 text-sm last:mb-0"><p className="font-semibold">{e.header || 'Role'}</p><p className="text-xs text-ink-500">{e.start} – {e.end} · {e.months} months</p><ul className="mt-1 list-disc pl-5 text-ink-700">{e.bullets.map((b) => <li key={b}>{b}</li>)}</ul></div>) : <p className="text-sm text-ink-500">No dated experience found.</p>}</Card>
        <Card title="Projects">{(p.projects || []).length ? p.projects.map((pr) => <div key={pr.name} className="mb-3 text-sm last:mb-0"><p className="font-semibold">{pr.name}</p><p className="text-ink-600">{pr.description}</p><div className="mt-1 flex flex-wrap gap-1">{pr.technologies.map((t) => <Badge key={t} tone="purple">{t}</Badge>)}</div></div>) : <p className="text-sm text-ink-500">No projects found.</p>}</Card>
        {(p.achievements || []).length > 0 && <Card title="Achievements"><ul className="list-disc space-y-1 pl-5 text-sm">{p.achievements.map((a) => <li key={a}>{a}</li>)}</ul></Card>}
      </div>
    </div>
  );
}

function ResumeView({ c }) {
  const [url, setUrl] = useState(null);
  useEffect(() => { api.get(`/candidates/${c.id}/resume-url/`).then((r) => setUrl(r.data.url)).catch(() => setUrl(null)); }, [c.id]);
  const full = url ? `${(import.meta.env.VITE_API_URL || '/api').replace(/\/api$/, '')}${url}` : null;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title={`Original resume · ${c.resume.original_filename}`}>
        {c.resume.file_type === 'pdf' && full ? <iframe title="Resume preview" src={full} className="h-[640px] w-full rounded-xl border border-gray-100" /> : (
          <div className="text-sm text-ink-600"><p>Word documents cannot be previewed in the browser.</p>{full && <a className="btn-secondary mt-3" href={full}>Download original</a>}</div>
        )}
      </Card>
      <Card title="Extracted text (basis for all findings)"><pre className="max-h-[640px] overflow-auto whitespace-pre-wrap text-xs leading-relaxed text-ink-700">{c.resume_text || 'No text extracted.'}</pre></Card>
    </div>
  );
}

export default function CandidateDetail() {
  const { id } = useParams();
  const { data: c, loading, error, reload } = useFetch(`/candidates/${id}/`);
  const [tab, setTab] = useState('analysis');
  if (loading) return <Spinner />;
  if (error || !c) return <Alert>{error || 'Candidate not found'}</Alert>;
  return (
    <>
      <PageHeader title={c.full_name} subtitle={`${c.email || 'No email'} · ${c.phone || 'No phone'} · applied for ${c.job_title}`}
        actions={<><StatusBadge status={c.status} />{c.match_score != null && <ScoreBadge value={c.match_score} suffix="/100" />}</>} />
      {c.duplicate_of && <Alert tone="amber" className="mb-4">Another resume with the same email exists for this job. <Link className="font-semibold underline" to={`/candidates/${c.duplicate_of}`}>View the other submission</Link>. This one is excluded from the proposed shortlist.</Alert>}
      <Tabs active={tab} onChange={setTab} tabs={[{ id: 'analysis', label: 'Assessment' }, { id: 'profile', label: 'Profile & corrections' }, { id: 'resume', label: 'Resume' }, { id: 'interviews', label: `Interviews (${c.sessions.length})` }]} />
      {tab === 'analysis' && <Analysis a={c.analysis} c={c} reload={reload} />}
      {tab === 'profile' && <ProfileEditor c={c} reload={reload} />}
      {tab === 'resume' && <ResumeView c={c} />}
      {tab === 'interviews' && (c.sessions.length ? <Card pad={false}><ul className="divide-y divide-gray-100">{c.sessions.map((s) => <li key={s.id} className="flex items-center justify-between px-5 py-3 text-sm"><Link className="font-semibold text-brand-700 hover:underline" to={`/interviews/${s.id}`}>Interview</Link><span className="flex items-center gap-3">{s.final_score != null && <ScoreBadge value={s.final_score} />}<StatusBadge status={s.status} /><span className="text-xs text-ink-500">{fmtDate(s.completed_at)}</span></span></li>)}</ul></Card> : <Empty title="No interviews">Add this candidate to an approved shortlist to interview them.</Empty>)}
    </>
  );
}
