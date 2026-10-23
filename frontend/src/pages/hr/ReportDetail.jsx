import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api, errorMessage } from '../../api/client';
import { Alert, BandBadge, Badge, Card, Field, PageHeader, ScoreBadge, Spinner, StatusBadge } from '../../components/ui';
import { useFetch } from '../../hooks/useFetch';
import { download, fmtDate, fmtDuration, fmtScore } from '../../lib/format';

const DECISIONS = [['selected', 'Selected', 'btn-primary'], ['on_hold', 'On hold', 'btn-secondary'], ['rejected', 'Rejected', 'btn-danger']];

export default function ReportDetail() {
  const { id } = useParams();
  const { data: p, loading, error, reload } = useFetch(`/interviews/${id}/report/`);
  const [comments, setComments] = useState('');
  const [msg, setMsg] = useState(null);
  const [open, setOpen] = useState({});
  if (loading) return <Spinner />;
  if (error || !p) return <Alert>{error || 'Report not available'}</Alert>;
  const r = p.report;
  if (!r) return <Alert tone="amber" title="Report not generated yet">The interview has not been completed. <Link to={`/interviews/${id}`} className="underline">Back to interview</Link></Alert>;

  const decide = async (decision) => {
    if (decision === 'rejected' && !window.confirm(`Record REJECTED for ${p.candidate.name}? This is your decision, not the AI’s.`)) return;
    setMsg(null);
    try { await api.post('/hr/decisions/', { session_id: id, decision, comments }); setComments(''); setMsg({ tone: 'green', text: 'Decision recorded.' }); reload(); }
    catch (e) { setMsg({ tone: 'red', text: errorMessage(e) }); }
  };
  const pdf = async () => { try { download((await api.get(`/interviews/${id}/report/pdf/`, { responseType: 'blob' })).data, `interview_report_${p.candidate.name.replace(/\s+/g, '_')}.pdf`); } catch (e) { setMsg({ tone: 'red', text: errorMessage(e) }); } };
  const regen = async () => { try { await api.post(`/interviews/${id}/report/regenerate/`); reload(); } catch (e) { setMsg({ tone: 'red', text: errorMessage(e) }); } };
  const chart = [['Resume', r.resume_score], ['General', r.general_score], ['Technical', r.technical_score], ['Final', r.final_score]].map(([name, value]) => ({ name, value }));
  const w = r.weights;

  return (
    <>
      <PageHeader title={p.candidate.name} subtitle={`${p.job.title} · interviewed ${fmtDate(p.interview_date)} · duration ${fmtDuration(p.duration_seconds)}`}
        actions={<><Link className="btn-secondary" to={`/interviews/${id}`}>Transcripts</Link><button className="btn-secondary" onClick={regen}>Recalculate</button><button className="btn-primary" onClick={pdf}>Download PDF</button></>} />
      {(p.is_mock || r.is_mock) && <Alert tone="red" title="MOCK TESTING MODE" className="mb-4">This report was produced with the mock provider and is not a real assessment.</Alert>}
      {msg && <Alert tone={msg.tone} className="mb-4">{msg.text}</Alert>}
      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Final assessment (advisory)" className="lg:col-span-1">
          <div className="flex items-end gap-2"><span className="text-5xl font-bold text-brand-700">{fmtScore(r.final_score, 2)}</span><span className="pb-2 text-ink-500">/ 100</span></div>
          <div className="mt-3"><BandBadge band={r.band} /></div>
          <dl className="mt-5 space-y-2 text-sm">
            {[['Resume match', r.resume_score, w.resume], ['General interview', r.general_score, w.general], ['Technical interview', r.technical_score, w.technical]].map(([l, v, wt]) => (
              <div key={l} className="flex justify-between"><dt className="text-ink-600">{l} <span className="text-xs text-ink-400">({wt}%)</span></dt><dd className="font-semibold">{fmtScore(v, 2)}</dd></div>))}
          </dl>
          <p className="mt-4 text-xs text-ink-500">Bands: 85–100 Strong · 70–84 Good · 50–69 Needs review · &lt;50 Significant gaps. They never accept or reject a candidate.</p>
        </Card>
        <Card title="Score breakdown" className="lg:col-span-2">
          <div className="h-56" role="img" aria-label="Bar chart of resume, general, technical and final scores"><ResponsiveContainer><BarChart data={chart}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="name" /><YAxis domain={[0, 100]} /><Tooltip /><Bar dataKey="value" radius={[8, 8, 0, 0]}>{chart.map((c, i) => <Cell key={c.name} fill={['#ddd6fe', '#a78bfa', '#7c3aed', '#2e1065'][i]} />)}</Bar></BarChart></ResponsiveContainer></div>
        </Card>
        <Card title="Job-related strengths">{r.strengths.length ? <ul className="space-y-2 text-sm">{r.strengths.map((s) => <li key={s.skill} className="flex justify-between"><span>{s.skill} <span className="text-xs text-ink-500">Q{s.questions.join(', Q')}</span></span><Badge tone="green">{s.avg_score}/10</Badge></li>)}</ul> : <p className="text-sm text-ink-500">None identified from the evidence.</p>}</Card>
        <Card title="Knowledge gaps">{r.knowledge_gaps.length ? <ul className="space-y-3 text-sm">{r.knowledge_gaps.map((s) => <li key={s.skill}><div className="flex justify-between"><span className="font-medium">{s.skill}</span><Badge tone="red">{s.avg_score}/10</Badge></div>{s.missing_points?.length > 0 && <p className="text-xs text-ink-500">Missing: {s.missing_points.join('; ')}</p>}</li>)}</ul> : <p className="text-sm text-ink-500">None identified from the evidence.</p>}</Card>
        <Card title="Coverage"><dl className="space-y-1 text-sm">{[['Questions', r.coverage.questions], ['Answered', r.coverage.answered], ['Evaluated', r.coverage.evaluated], ['Unavailable / skipped', r.coverage.unavailable], ['Pending / failed', r.coverage.failed]].map(([l, v]) => <div key={l} className="flex justify-between"><dt className="text-ink-600">{l}</dt><dd className="font-semibold">{v}</dd></div>)}</dl></Card>
        <Card title="AI-generated summary" className="lg:col-span-3"><p className="text-sm leading-relaxed text-ink-800">{r.summary}</p>
          <p className="label mt-4">Uncertainty &amp; limitations</p><ul className="list-disc space-y-1 pl-5 text-xs text-ink-600">{r.uncertainty.map((u) => <li key={u}>{u}</li>)}</ul></Card>
        <Card title="Final HR decision" className="lg:col-span-3">
          {p.latest_decision ? <div className="mb-4 flex flex-wrap items-center gap-3 text-sm"><StatusBadge status={p.latest_decision.decision} /><span>by <b>{p.latest_decision.decided_by}</b> on {fmtDate(p.latest_decision.decided_at)}</span>{p.latest_decision.comments && <span className="text-ink-600">“{p.latest_decision.comments}”</span>}</div>
            : <Alert tone="amber" className="mb-4">No decision recorded. Only an authorised HR user can select, reject or hold a candidate.</Alert>}
          <Field label="HR comments">{(i) => <textarea id={i} className="input min-h-[70px]" value={comments} onChange={(e) => setComments(e.target.value)} placeholder="Reasoning behind your decision (recommended)" />}</Field>
          <div className="mt-3 flex flex-wrap gap-2">{DECISIONS.map(([v, l, cls]) => <button key={v} className={cls} onClick={() => decide(v)}>{p.latest_decision ? 'Change to ' : 'Mark '}{l}</button>)}</div>
          {p.decisions.length > 1 && <ul className="mt-4 space-y-1 border-t border-gray-100 pt-3 text-xs text-ink-500">{p.decisions.slice(1).map((d) => <li key={d.id}>{fmtDate(d.decided_at)} – {d.decision.replace('_', ' ')} by {d.decided_by}{d.comments ? `: ${d.comments}` : ''}</li>)}</ul>}
        </Card>
        <Card title="Question-by-question breakdown" className="lg:col-span-3" pad={false}>
          <ul className="divide-y divide-gray-100">{p.questions.map((q) => {
            const ev = q.evaluation;
            return (
              <li key={q.number} className="px-5 py-3 text-sm">
                <button className="flex w-full items-start justify-between gap-3 text-left" aria-expanded={!!open[q.number]} onClick={() => setOpen({ ...open, [q.number]: !open[q.number] })}>
                  <span><b>Q{q.number}</b> <Badge tone={q.section === 'general' ? 'blue' : 'purple'}>{q.section}</Badge> {q.question}</span>
                  {ev?.status === 'completed' ? <ScoreBadge value={ev.effective_score} suffix="/10" /> : <Badge>{ev?.status || 'n/a'}</Badge>}
                </button>
                {open[q.number] && (
                  <div className="mt-3 space-y-2 rounded-xl bg-gray-50 p-3">
                    <p className="whitespace-pre-wrap text-ink-700"><b>Answer:</b> {q.answer?.text || '(none)'}</p>
                    {ev?.status === 'completed' && <>
                      {ev.positive_points.length > 0 && <p><b>Strong:</b> {ev.positive_points.join('; ')}</p>}
                      {ev.missing_points.length > 0 && <p><b>Missing:</b> {ev.missing_points.join('; ')}</p>}
                      {ev.inaccuracies.length > 0 && <p className="text-red-700"><b>Possible inaccuracies:</b> {ev.inaccuracies.join('; ')}</p>}
                      <p><b>Feedback:</b> {ev.feedback}</p>
                      <p className="text-xs text-ink-500">Confidence {ev.confidence} · {Object.entries(ev.criterion_scores).map(([k, v]) => `${k.replace('_', ' ')} ${v}`).join(' · ')}</p>
                    </>}
                  </div>
                )}
              </li>
            );
          })}</ul>
        </Card>
      </div>
    </>
  );
}
