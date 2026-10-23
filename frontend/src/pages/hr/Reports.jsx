import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api, errorMessage } from '../../api/client';
import { Alert, BandBadge, Card, Empty, PageHeader, ScoreBadge, Spinner, StatusBadge } from '../../components/ui';
import { results, useFetch } from '../../hooks/useFetch';
import { download, fmtDate, fmtScore } from '../../lib/format';

export default function Reports() {
  const jobs = useFetch('/jobs/', { params: { page_size: 100 } });
  const [job, setJob] = useState('');
  const { data, loading, error } = useFetch('/interviews/', { params: { status: 'completed', page_size: 200, ...(job ? { job } : {}) } });
  const [picked, setPicked] = useState([]);
  const [cmp, setCmp] = useState(null);
  const [err, setErr] = useState('');
  const rows = results(data).sort((a, b) => (b.final_score ?? -1) - (a.final_score ?? -1));

  const toggle = (id) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : p.length < 6 ? [...p, id] : p));
  const compare = async () => { setErr(''); try { setCmp((await api.get('/reports/compare/', { params: { sessions: picked.join(',') } })).data); } catch (e) { setErr(errorMessage(e)); } };
  const exportCsv = async () => { try { const r = await api.get('/reports/export/', { params: job ? { job } : {}, responseType: 'blob' }); download(r.data, 'interview_results.csv'); } catch (e) { setErr(errorMessage(e)); } };
  const chart = cmp?.candidates.map((c) => ({ name: c.candidate.split(' ')[0], Resume: c.resume_score, General: c.general_score, Technical: c.technical_score, Final: c.final_score }));

  return (
    <>
      <PageHeader title="Reports" subtitle="Completed interviews. Scores and bands are advisory; the final decision is yours."
        actions={<><button className="btn-secondary" onClick={exportCsv}>Export CSV</button><button className="btn-primary" disabled={picked.length < 2} onClick={compare}>Compare selected ({picked.length})</button></>} />
      {err && <Alert className="mb-4">{err}</Alert>}
      <Card pad={false}>
        <div className="flex gap-3 border-b border-gray-100 px-5 py-3">
          <select aria-label="Filter by job" className="input !w-64" value={job} onChange={(e) => setJob(e.target.value)}><option value="">All jobs</option>{results(jobs.data).map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}</select>
          <span className="self-center text-xs text-ink-500">Select 2–6 candidates to compare.</span>
        </div>
        {loading ? <Spinner /> : error ? <div className="p-5"><Alert>{error}</Alert></div> : !rows.length ? <div className="p-5"><Empty title="No completed interviews yet" /></div> : (
          <div className="overflow-x-auto"><table className="min-w-full divide-y divide-gray-100">
            <thead className="bg-gray-50/70"><tr><th className="th w-10" /><th className="th">Candidate</th><th className="th">Job</th><th className="th">Final score</th><th className="th">Band (advisory)</th><th className="th">HR decision</th><th className="th">Completed</th></tr></thead>
            <tbody className="divide-y divide-gray-100">{rows.map((r) => (
              <tr key={r.id} className="hover:bg-brand-50/40">
                <td className="td"><input type="checkbox" aria-label={`Select ${r.candidate_name} for comparison`} className="h-4 w-4 accent-brand-700" checked={picked.includes(r.id)} onChange={() => toggle(r.id)} /></td>
                <td className="td"><Link to={`/reports/${r.id}`} className="font-semibold text-brand-700 hover:underline">{r.candidate_name}</Link></td>
                <td className="td">{r.job_title}</td><td className="td"><ScoreBadge value={r.final_score} /></td><td className="td"><BandBadge band={r.band} /></td>
                <td className="td">{r.decision ? <StatusBadge status={r.decision} /> : <span className="text-xs font-semibold text-amber-700">Pending HR decision</span>}</td>
                <td className="td text-ink-500">{fmtDate(r.completed_at)}</td>
              </tr>))}</tbody></table></div>
        )}
      </Card>
      {cmp && (
        <Card title="Candidate comparison" className="mt-6">
          <Alert tone="blue" className="mb-4">{cmp.notice}</Alert>
          <div className="h-72" role="img" aria-label="Grouped bar chart comparing resume, general, technical and final scores"><ResponsiveContainer><BarChart data={chart}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="name" /><YAxis domain={[0, 100]} /><Tooltip /><Legend />
            <Bar dataKey="Resume" fill="#ddd6fe" radius={[4, 4, 0, 0]} /><Bar dataKey="General" fill="#a78bfa" radius={[4, 4, 0, 0]} /><Bar dataKey="Technical" fill="#7c3aed" radius={[4, 4, 0, 0]} /><Bar dataKey="Final" fill="#2e1065" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></div>
          {Object.keys(cmp.skills).length > 0 && (
            <div className="mt-6 overflow-x-auto"><table className="min-w-full text-sm"><thead><tr><th className="th">Skill area (avg /10)</th>{cmp.candidates.map((c) => <th key={c.session_id} className="th">{c.candidate}</th>)}</tr></thead>
              <tbody className="divide-y divide-gray-100">{Object.entries(cmp.skills).map(([skill, byC]) => <tr key={skill}><td className="td font-medium">{skill}</td>{cmp.candidates.map((c) => <td key={c.session_id} className="td">{byC[c.candidate] != null ? fmtScore(byC[c.candidate]) : '—'}</td>)}</tr>)}</tbody></table></div>
          )}
        </Card>
      )}
    </>
  );
}
