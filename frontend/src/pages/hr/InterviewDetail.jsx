import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, errorMessage } from '../../api/client';
import { Alert, Badge, Card, CopyButton, Empty, Field, PageHeader, ProgressBar, ScoreBadge, Spinner, StatusBadge, Tabs } from '../../components/ui';
import { useFetch } from '../../hooks/useFetch';
import { fmtDate, fmtDuration } from '../../lib/format';

function QuestionRow({ q, editable, sessionId, onSaved }) {
  const [edit, setEdit] = useState(false);
  const [text, setText] = useState(q.question);
  const [points, setPoints] = useState((q.expected_points || []).join('\n'));
  const [msg, setMsg] = useState(null);
  const save = async () => {
    try {
      const r = await api.patch(`/interviews/${sessionId}/questions/${q.id}/`, { text, expected_points: points.split('\n').map((s) => s.trim()).filter(Boolean) });
      setMsg(r.data.warnings?.length ? { tone: 'amber', text: r.data.warnings.join(' ') } : null);
      setEdit(false); onSaved();
    } catch (e) { setMsg({ tone: 'red', text: errorMessage(e) }); }
  };
  return (
    <li className="px-5 py-4">
      <div className="flex items-start gap-3">
        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-brand-50 text-xs font-bold text-brand-700">{q.number}</span>
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-2"><Badge tone={q.section === 'general' ? 'blue' : 'purple'}>{q.section}</Badge>{q.difficulty && <Badge>{q.difficulty}</Badge>}{q.skill_tags?.map((t) => <Badge key={t} tone="gray">{t}</Badge>)}{q.edited && <Badge tone="amber">edited by HR</Badge>}</div>
          {edit ? (
            <div className="space-y-2">
              <textarea aria-label={`Question ${q.number} text`} className="input min-h-[70px]" value={text} onChange={(e) => setText(e.target.value)} />
              <Field label="Reference points (one per line, hidden from candidate)">{(id) => <textarea id={id} className="input min-h-[70px]" value={points} onChange={(e) => setPoints(e.target.value)} />}</Field>
              <div className="flex gap-2"><button className="btn-primary" onClick={save}>Save</button><button className="btn-secondary" onClick={() => setEdit(false)}>Cancel</button></div>
            </div>
          ) : (
            <>
              <p className="text-sm font-medium text-ink-900">{q.question}</p>
              {q.expected_points?.length > 0 && <p className="mt-1 text-xs text-ink-500">Reference points: {q.expected_points.join(' · ')}</p>}
              {q.grounding?.length > 0 && <p className="mt-0.5 text-xs text-ink-500">Based on: {q.grounding.join(' · ')}</p>}
              {editable && <button className="btn-ghost mt-1 !px-2 !py-1 text-xs" onClick={() => setEdit(true)}>Edit question</button>}
            </>
          )}
          {msg && <Alert tone={msg.tone} className="mt-2">{msg.text}</Alert>}
        </div>
      </div>
    </li>
  );
}

function AnswerRow({ q, sessionId, onChanged }) {
  const [audio, setAudio] = useState(null);
  const [ov, setOv] = useState({ open: false, score: '', reason: '' });
  const [err, setErr] = useState('');
  const ev = q.evaluation, ans = q.answer;
  const loadAudio = async () => {
    try { const r = await api.get(`/interviews/${sessionId}/answers/${ans.id}/audio-url/`); setAudio(`${(import.meta.env.VITE_API_URL || '/api').replace(/\/api$/, '')}${r.data.url}`); }
    catch (e) { setErr(errorMessage(e)); }
  };
  const override = async (e) => {
    e.preventDefault();
    try { await api.post(`/interviews/${sessionId}/overrides/`, { answer_id: ans.id, score: Number(ov.score), reason: ov.reason }); setOv({ open: false, score: '', reason: '' }); onChanged(); }
    catch (ex) { setErr(errorMessage(ex)); }
  };
  return (
    <li className="px-5 py-4 text-sm">
      <div className="flex items-start justify-between gap-3">
        <p className="font-semibold text-ink-900">Q{q.number}. {q.question}</p>
        {ev?.status === 'completed' ? <ScoreBadge value={ev.effective_score} suffix="/10" /> : ev ? <Badge tone={ev.status === 'failed' ? 'red' : 'gray'}>{ev.status}</Badge> : <Badge>not answered</Badge>}
      </div>
      {ans ? (
        <>
          <div className="mt-2 rounded-xl bg-gray-50 p-3"><p className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-500">{ans.input_mode === 'voice' ? `Transcript (${ans.transcript_source})` : 'Typed answer'} · {fmtDate(ans.submitted_at)}</p><p className="whitespace-pre-wrap text-ink-800">{ans.text || '(skipped / unavailable)'}</p></div>
          {ans.has_audio && (audio ? <audio controls src={audio} className="mt-2 w-full" /> : <button className="btn-secondary mt-2" onClick={loadAudio}>▶ Load recording</button>)}
        </>
      ) : <p className="mt-1 text-ink-500">No answer yet.</p>}
      {ev?.status === 'completed' && (
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {ev.positive_points.length > 0 && <div><p className="label">Strong points</p><ul className="list-disc pl-5 text-ink-700">{ev.positive_points.map((p) => <li key={p}>{p}</li>)}</ul></div>}
          {ev.missing_points.length > 0 && <div><p className="label">Missing</p><ul className="list-disc pl-5 text-ink-700">{ev.missing_points.map((p) => <li key={p}>{p}</li>)}</ul></div>}
          {ev.inaccuracies.length > 0 && <div><p className="label">Potential inaccuracies</p><ul className="list-disc pl-5 text-red-700">{ev.inaccuracies.map((p) => <li key={p}>{p}</li>)}</ul></div>}
          <div className="sm:col-span-2"><p className="text-ink-700">{ev.feedback}</p><p className="mt-1 text-xs text-ink-500">Criteria: {Object.entries(ev.criterion_scores).map(([k, v]) => `${k.replace('_', ' ')} ${v}`).join(' · ')} · AI confidence {ev.confidence ?? '—'}{ev.is_mock ? ' · MOCK' : ''}</p>
            {ev.evidence.length > 0 && <p className="mt-1 text-xs text-ink-500">Evidence: {ev.evidence.map((e) => `“${e.quote}”`).join(', ')}</p>}
            {ev.hr_override_score != null && <p className="mt-1 text-xs font-semibold text-amber-800">HR adjusted to {ev.hr_override_score}/10: {ev.hr_override_reason}</p>}</div>
          {!ov.open ? <button className="btn-ghost justify-self-start !px-2 !py-1 text-xs" onClick={() => setOv({ ...ov, open: true })}>Dispute / adjust score</button> : (
            <form onSubmit={override} className="flex flex-wrap items-end gap-2 sm:col-span-2">
              <Field label="Score 0–10">{(id) => <input id={id} className="input !w-24" type="number" min="0" max="10" step="0.5" required value={ov.score} onChange={(e) => setOv({ ...ov, score: e.target.value })} />}</Field>
              <div className="min-w-[14rem] flex-1"><Field label="Reason">{(id) => <input id={id} className="input" required minLength={5} value={ov.reason} onChange={(e) => setOv({ ...ov, reason: e.target.value })} />}</Field></div>
              <button className="btn-primary">Save</button><button type="button" className="btn-secondary" onClick={() => setOv({ ...ov, open: false })}>Cancel</button>
            </form>
          )}
        </div>
      )}
      {err && <Alert className="mt-2">{err}</Alert>}
    </li>
  );
}

function Invitation({ s, reload }) {
  const [days, setDays] = useState(7);
  const [email, setEmail] = useState(true);
  const [link, setLink] = useState(null);
  const [err, setErr] = useState('');
  const act = async (fn) => { setErr(''); try { await fn(); reload(); } catch (e) { setErr(errorMessage(e)); } };
  const create = () => act(async () => { const r = await api.post('/interviews/create/', { session_id: s.id, expires_in_days: Number(days), send_email: email }); setLink(r.data); });
  const regen = () => act(async () => { const r = await api.post(`/interviews/${s.id}/regenerate-link/`, { send_email: email }); setLink(r.data); });
  const revoke = () => act(() => api.post(`/interviews/${s.id}/revoke/`));
  return (
    <Card title="Candidate invitation">
      {err && <Alert className="mb-3">{err}</Alert>}
      {link && (
        <Alert tone="green" title="Personal interview link (shown only once – copy it now)" className="mb-3">
          <div className="mt-1 flex flex-wrap items-center gap-2"><code className="break-all rounded bg-white/70 px-2 py-1 text-xs">{link.link}</code><CopyButton text={link.link} /></div>
          <p className="mt-1 text-xs">{link.email_sent ? 'An email was sent to the candidate.' : 'No email was sent – share the link yourself.'} Expires {fmtDate(link.expires_at)}.</p>
        </Alert>
      )}
      {!s.has_invitation ? (
        s.status === 'ready' ? (
          <div className="flex flex-wrap items-end gap-3">
            <Field label="Link valid for (days)">{(id) => <input id={id} type="number" min="1" max="60" className="input !w-28" value={days} onChange={(e) => setDays(e.target.value)} />}</Field>
            <label className="flex items-center gap-2 pb-2 text-sm"><input type="checkbox" className="h-4 w-4 accent-brand-700" checked={email} onChange={(e) => setEmail(e.target.checked)} />Email the candidate</label>
            <button className="btn-primary" onClick={create}>Approve &amp; create invitation</button>
          </div>
        ) : <p className="text-sm text-ink-500">Approve the 20 questions first to enable the invitation.</p>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
          <div><Badge tone={s.invitation_status === 'revoked' ? 'red' : 'purple'}>{s.invitation_status}</Badge><span className="ml-2 text-ink-500">expires {fmtDate(s.invitation_expires_at)}</span></div>
          {s.status !== 'completed' && <div className="flex gap-2"><button className="btn-secondary" onClick={regen}>Issue new link</button><button className="btn-secondary" onClick={revoke}>Revoke</button></div>}
        </div>
      )}
    </Card>
  );
}

export default function InterviewDetail() {
  const { id } = useParams();
  const { data: s, loading, error, reload } = useFetch(`/interviews/${id}/`, { interval: 5000 });
  const [tab, setTab] = useState('questions');
  const [msg, setMsg] = useState(null);
  if (loading) return <Spinner />;
  if (error || !s) return <Alert>{error || 'Interview not found'}</Alert>;
  const editable = ['draft', 'ready'].includes(s.status) && s.answered === 0;
  const act = async (fn, ok) => { setMsg(null); try { await fn(); if (ok) setMsg({ tone: 'green', text: ok }); reload(); } catch (e) { setMsg({ tone: 'red', text: errorMessage(e) }); } };

  return (
    <>
      <PageHeader title={s.candidate_name} subtitle={`${s.job_title} · created ${fmtDate(s.created_at)}${s.duration_seconds ? ` · duration ${fmtDuration(s.duration_seconds)}` : ''}`}
        actions={<><StatusBadge status={s.status} />{s.status === 'completed' && <Link className="btn-primary" to={`/reports/${s.id}`}>Open report</Link>}</>} />
      {s.is_mock && <Alert tone="red" title="Mock testing mode" className="mb-4">These questions/evaluations came from the mock provider and must not be used for real hiring decisions.</Alert>}
      {msg && <Alert tone={msg.tone} className="mb-4">{msg.text}</Alert>}
      {s.status === 'generating_questions' && <Alert tone="blue" className="mb-4">Generating the 20 interview questions… this page refreshes automatically.</Alert>}
      {s.status === 'generation_failed' && (
        <Alert title="Question generation failed" className="mb-4">{s.generation_error}
          <div className="mt-2"><button className="btn-secondary" onClick={() => act(() => api.post(`/interviews/${id}/generate-questions/`), 'Generation restarted.')}>Retry generation</button> <Link to="/settings" className="ml-2 font-semibold underline">AI settings</Link></div>
        </Alert>
      )}
      <div className="mb-6 grid gap-6 lg:grid-cols-2">
        {s.status === 'draft' && <Card title="Step 1 · Review questions"><p className="text-sm text-ink-600">Review and edit the 20 questions below. Candidates only ever see one question at a time. Editing re-opens approval.</p><button className="btn-primary mt-3" onClick={() => act(() => api.post(`/interviews/${id}/approve-questions/`), 'Questions approved.')}>Approve all 20 questions</button></Card>}
        {['ready', 'in_progress', 'completed', 'draft'].includes(s.status) && <Invitation s={s} reload={reload} />}
        {['in_progress', 'completed'].includes(s.status) && (
          <Card title="Progress"><ProgressBar value={s.answered} max={s.total} label="Answered questions" /><p className="mt-2 text-sm text-ink-600">{s.answered} of {s.total} answered · recording consent: {s.recording_consent ? 'given' : 'not given'}</p>
            <label className="mt-3 flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4 accent-brand-700" checked={s.reveal_results} onChange={(e) => act(() => api.patch(`/interviews/${id}/`, { reveal_results: e.target.checked }))} />Show per-answer feedback to the candidate (off by default)</label></Card>
        )}
      </div>
      <Tabs active={tab} onChange={setTab} tabs={[{ id: 'questions', label: 'Questions' }, { id: 'answers', label: 'Answers & evaluation' }]} />
      {tab === 'questions' && (s.questions.length ? <Card pad={false}><ul className="divide-y divide-gray-100">{s.questions.map((q) => <QuestionRow key={q.id} q={q} editable={editable} sessionId={id} onSaved={reload} />)}</ul></Card> : <Empty title="No questions yet" />)}
      {tab === 'answers' && (s.answered ? <Card pad={false}><ul className="divide-y divide-gray-100">{s.questions.map((q) => <AnswerRow key={q.id} q={q} sessionId={id} onChanged={reload} />)}</ul></Card> : <Empty title="No answers yet">Answers, transcripts and evaluations appear here as the candidate progresses.</Empty>)}
    </>
  );
}
