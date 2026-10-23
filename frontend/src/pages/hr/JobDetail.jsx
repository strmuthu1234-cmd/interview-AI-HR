import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, errorMessage } from '../../api/client';
import { Alert, Badge, Card, Empty, PageHeader, ProgressBar, ScoreBadge, Spinner, StatusBadge, Tabs } from '../../components/ui';
import { results, useFetch } from '../../hooks/useFetch';
import { fmtDate } from '../../lib/format';
import { JobForm } from './Jobs';

const MAX_FILES = 50;
const MAX_MB = 5;

export function validateSelection(existing, incoming) {
  const accepted = [], problems = [];
  const names = new Set(existing.map((f) => `${f.name}:${f.size}`));
  for (const f of incoming) {
    const ext = f.name.split('.').pop().toLowerCase();
    if (!['pdf', 'docx'].includes(ext)) problems.push(`${f.name}: only PDF and DOCX files are supported`);
    else if (f.size > MAX_MB * 1024 * 1024) problems.push(`${f.name}: larger than ${MAX_MB} MB`);
    else if (f.size === 0) problems.push(`${f.name}: file is empty`);
    else if (names.has(`${f.name}:${f.size}`)) problems.push(`${f.name}: already selected`);
    else if (existing.length + accepted.length >= MAX_FILES) { problems.push(`${f.name}: limit of ${MAX_FILES} resumes per batch reached`); }
    else { accepted.push(f); names.add(`${f.name}:${f.size}`); }
  }
  return { accepted, problems };
}

function UploadZone({ jobId, onUploaded }) {
  const [files, setFiles] = useState([]);
  const [problems, setProblems] = useState([]);
  const [drag, setDrag] = useState(false);
  const [progress, setProgress] = useState(null);
  const [outcome, setOutcome] = useState(null);
  const [error, setError] = useState('');
  const input = useRef(null);

  const add = (list) => {
    const { accepted, problems: p } = validateSelection(files, Array.from(list));
    setFiles([...files, ...accepted]);
    setProblems(p);
  };
  const upload = async () => {
    const fd = new FormData();
    fd.append('job', jobId);
    files.forEach((f) => fd.append('files', f));
    setProgress(0); setError(''); setOutcome(null);
    try {
      const r = await api.post('/resumes/bulk-upload/', fd, { onUploadProgress: (e) => setProgress(e.total ? Math.round((e.loaded / e.total) * 100) : 50), timeout: 600000 });
      setOutcome(r.data); setFiles([]); onUploaded(r.data);
    } catch (e) { setError(errorMessage(e)); }
    finally { setProgress(null); }
  };

  return (
    <Card title="Upload resumes" action={<span className="text-xs text-ink-500">1–{MAX_FILES} PDF or DOCX files · max {MAX_MB} MB each</span>}>
      <div role="button" tabIndex={0} aria-label="Drop resumes here or press Enter to browse"
        onClick={() => input.current?.click()} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && input.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); add(e.dataTransfer.files); }}
        className={`cursor-pointer rounded-2xl border-2 border-dashed px-6 py-10 text-center transition ${drag ? 'border-brand-500 bg-brand-50' : 'border-gray-200 hover:border-brand-300 hover:bg-brand-50/40'}`}>
        <p className="font-semibold text-ink-900">Drag &amp; drop resumes here</p>
        <p className="mt-1 text-sm text-ink-500">or click to choose files</p>
        <input ref={input} data-testid="file-input" type="file" multiple accept=".pdf,.docx" className="hidden" onChange={(e) => { add(e.target.files); e.target.value = ''; }} />
      </div>
      {problems.length > 0 && <Alert tone="amber" title="Some files were not added" className="mt-3"><ul className="list-disc pl-5">{problems.slice(0, 8).map((p) => <li key={p}>{p}</li>)}{problems.length > 8 && <li>…and {problems.length - 8} more</li>}</ul></Alert>}
      {files.length > 0 && (
        <div className="mt-4">
          <div className="mb-2 flex items-center justify-between"><p className="text-sm font-semibold">{files.length} file{files.length > 1 ? 's' : ''} selected</p><button className="btn-ghost" onClick={() => setFiles([])} disabled={progress !== null}>Clear</button></div>
          <ul className="max-h-40 divide-y divide-gray-100 overflow-y-auto rounded-xl border border-gray-100 text-sm">
            {files.map((f) => <li key={f.name + f.size} className="flex items-center justify-between px-3 py-1.5"><span className="truncate">{f.name}</span><button aria-label={`Remove ${f.name}`} className="text-ink-400 hover:text-red-600" onClick={() => setFiles(files.filter((x) => x !== f))}>✕</button></li>)}
          </ul>
          {progress !== null ? <div className="mt-3"><ProgressBar value={progress} label="Upload progress" /><p className="mt-1 text-xs text-ink-500">Uploading… {progress}%</p></div>
            : <button className="btn-primary mt-3" onClick={upload}>Upload &amp; screen {files.length} resume{files.length > 1 ? 's' : ''}</button>}
        </div>
      )}
      {error && <Alert className="mt-3">{error}</Alert>}
      {outcome && (
        <Alert tone={outcome.rejected ? 'amber' : 'green'} title={`${outcome.accepted} accepted · ${outcome.rejected} rejected`} className="mt-3">
          {outcome.results.filter((r) => r.status === 'rejected').map((r) => <p key={r.filename}>• {r.filename}: {r.reason}</p>)}
          {outcome.accepted > 0 && <p>Screening is running in the background; results appear below.</p>}
        </Alert>
      )}
    </Card>
  );
}

function BatchHistory({ batches }) {
  if (!batches.length) return null;
  return (
    <Card title="Batch history" pad={false}>
      <ul className="divide-y divide-gray-100">
        {batches.map((b) => {
          const done = b.processed_count + b.failed_count;
          return (
            <li key={b.id} className="flex flex-wrap items-center gap-4 px-5 py-3 text-sm">
              <div className="w-44 text-ink-600">{fmtDate(b.created_at)}</div>
              <StatusBadge status={b.status === 'processing' ? 'in_progress' : b.status} />
              <div className="min-w-[10rem] flex-1"><ProgressBar value={done} max={Math.max(1, b.accepted_files)} label="Screening progress" tone={b.status === 'completed' ? 'green' : 'brand'} /></div>
              <div className="text-xs text-ink-500">{done}/{b.accepted_files} screened{b.failed_count ? ` · ${b.failed_count} failed` : ''}{b.rejected_files?.length ? ` · ${b.rejected_files.length} rejected` : ''}</div>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function Screening({ job }) {
  const nav = useNavigate();
  const batches = useFetch('/batches/', { params: { job: job.id } });
  const processing = results(batches.data).some((b) => b.status === 'processing');
  const cands = useFetch('/candidates/', { params: { job: job.id, page_size: 200 }, interval: processing ? 3000 : undefined });
  const shortlist = useFetch('/shortlists/', { params: { job: job.id, status: 'proposed' } });
  useEffect(() => { if (processing) { const t = setInterval(() => { batches.reload(true); shortlist.reload(true); }, 3000); return () => clearInterval(t); } return undefined; }, [processing]); // eslint-disable-line

  const [selected, setSelected] = useState(null);
  const [filters, setFilters] = useState({ minScore: '', skill: '', status: '' });
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  const proposed = results(shortlist.data)[0];
  const proposedKey = proposed ? `${proposed.id}:${proposed.entries.map((e) => e.candidate_id).join(',')}` : '';
  useEffect(() => { if (proposed) setSelected(new Set(proposed.entries.map((e) => e.candidate_id))); else setSelected(new Set()); }, [proposedKey]); // eslint-disable-line

  const rows = useMemo(() => {
    let r = [...results(cands.data)];
    if (filters.minScore) r = r.filter((c) => (c.match_score ?? -1) >= Number(filters.minScore));
    if (filters.skill) r = r.filter((c) => c.matching_skills.some((s) => s.toLowerCase().includes(filters.skill.toLowerCase())));
    if (filters.status) r = r.filter((c) => c.status === filters.status);
    return r.sort((a, b) => (b.match_score ?? -1) - (a.match_score ?? -1));
  }, [cands.data, filters]);

  const toggle = (id) => setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const approve = async () => {
    setBusy(true); setMsg(null);
    try {
      const r = await api.post('/shortlists/approve/', { shortlist_id: proposed.id, candidate_ids: [...selected] });
      setMsg({ tone: 'green', text: `Shortlist approved. Generating 20 questions for ${r.data.interview_sessions.length} candidates – review them under Interviews.` });
      shortlist.reload(); cands.reload();
    } catch (e) { setMsg({ tone: 'red', text: errorMessage(e) }); }
    finally { setBusy(false); }
  };
  const reanalyze = async () => {
    try { await api.post('/resumes/analyze/', { job_id: job.id }); setMsg({ tone: 'blue', text: 'Re-scoring all resumes with the current rubric…' }); setTimeout(() => { cands.reload(); shortlist.reload(); }, 2500); }
    catch (e) { setMsg({ tone: 'red', text: errorMessage(e) }); }
  };
  const afterUpload = () => { batches.reload(); cands.reload(); shortlist.reload(); };
  const eligible = (c) => c.status === 'screened';

  return (
    <div className="space-y-6">
      <UploadZone jobId={job.id} onUploaded={afterUpload} />
      <BatchHistory batches={results(batches.data)} />
      {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
      <Card title={`Ranked candidates (${rows.length})`} pad={false}
        action={<div className="flex gap-2"><button className="btn-secondary" onClick={reanalyze}>Re-score</button></div>}>
        <div className="flex flex-wrap gap-3 border-b border-gray-100 px-5 py-3">
          <input aria-label="Minimum score" className="input !w-36" type="number" min="0" max="100" placeholder="Min. score" value={filters.minScore} onChange={(e) => setFilters({ ...filters, minScore: e.target.value })} />
          <input aria-label="Filter by skill" className="input !w-48" placeholder="Matching skill…" value={filters.skill} onChange={(e) => setFilters({ ...filters, skill: e.target.value })} />
          <select aria-label="Filter by status" className="input !w-44" value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}>
            <option value="">All statuses</option>{['screened', 'shortlisted', 'interview_invited', 'interviewed', 'selected', 'rejected', 'on_hold'].map((s) => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
          </select>
        </div>
        {cands.loading ? <Spinner /> : !rows.length ? <div className="p-5"><Empty title="No candidates match">Upload resumes above to see AI-ranked candidates.</Empty></div> : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-100">
              <thead className="bg-gray-50/70"><tr><th className="th w-10">Pick</th><th className="th">#</th><th className="th">Candidate</th><th className="th">Match</th><th className="th">Missing required</th><th className="th">Status</th><th className="th">Flags</th></tr></thead>
              <tbody className="divide-y divide-gray-100">
                {rows.map((c, i) => (
                  <tr key={c.id} className="hover:bg-brand-50/40">
                    <td className="td"><input type="checkbox" aria-label={`Shortlist ${c.full_name}`} disabled={!eligible(c) || !proposed} checked={selected?.has(c.id) || false} onChange={() => toggle(c.id)} className="h-4 w-4 accent-brand-700" /></td>
                    <td className="td text-ink-500">{i + 1}</td>
                    <td className="td"><Link to={`/candidates/${c.id}`} className="font-semibold text-brand-700 hover:underline">{c.full_name || c.resume_filename}</Link><div className="text-xs text-ink-500">{c.resume_filename}</div></td>
                    <td className="td">{c.parse_status === 'failed' ? <Badge tone="red">Unreadable</Badge> : <ScoreBadge value={c.match_score} />}</td>
                    <td className="td max-w-xs">{c.parse_status === 'failed' ? <span className="text-xs text-red-700">{c.parse_error}</span> : c.missing_required_skills.length ? <div className="flex flex-wrap gap-1">{c.missing_required_skills.map((s) => <Badge key={s} tone="red">{s}</Badge>)}</div> : <span className="text-xs text-emerald-700">None</span>}</td>
                    <td className="td"><StatusBadge status={c.status} /></td>
                    <td className="td space-x-1">{c.duplicate_of && <Badge tone="amber">Possible duplicate</Badge>}{c.security_flag_count > 0 && <Badge tone="red">Injection text ignored</Badge>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {proposed && (
        <Card title="Proposed shortlist" action={<Badge tone="purple">{selected?.size || 0} / {job.shortlist_size} slots</Badge>}>
          <p className="text-sm text-ink-600">The top {job.shortlist_size} by match score are pre-selected{results(cands.data).length < job.shortlist_size ? ` (only ${results(cands.data).length} candidates uploaded, so none are invented)` : ''}. Add or remove candidates with the checkboxes above, then approve. Interviews are only created after your approval.</p>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button className="btn-primary" disabled={busy || !selected?.size || selected.size > job.shortlist_size} onClick={approve}>{busy ? 'Approving…' : 'Approve shortlist & generate questions'}</button>
            {selected?.size > job.shortlist_size && <span className="text-sm text-red-600">Too many selected – increase the job’s shortlist slots or deselect candidates.</span>}
          </div>
        </Card>
      )}
    </div>
  );
}

function JobInterviews({ jobId }) {
  const { data, loading } = useFetch('/interviews/', { params: { job: jobId, page_size: 100 } });
  const rows = results(data);
  if (loading) return <Spinner />;
  if (!rows.length) return <Empty title="No interviews yet">Approve a shortlist to create interviews.</Empty>;
  return (
    <Card pad={false}><ul className="divide-y divide-gray-100">{rows.map((s) => (
      <li key={s.id} className="flex items-center justify-between gap-3 px-5 py-3"><Link className="font-semibold text-brand-700 hover:underline" to={`/interviews/${s.id}`}>{s.candidate_name}</Link><div className="flex items-center gap-2"><span className="text-xs text-ink-500">{s.answered}/{s.total} answered</span><StatusBadge status={s.status} /></div></li>
    ))}</ul></Card>
  );
}

export default function JobDetail() {
  const { id } = useParams();
  const { data: job, loading, error, reload } = useFetch(`/jobs/${id}/`);
  const [tab, setTab] = useState('screening');
  const [saved, setSaved] = useState(false);
  const onSaved = useCallback(() => { setSaved(true); reload(); setTimeout(() => setSaved(false), 2500); }, [reload]);
  if (loading) return <Spinner />;
  if (error || !job) return <Alert>{error || 'Job not found'}</Alert>;
  return (
    <>
      <PageHeader title={job.title} subtitle={`${job.department || 'No department'} · ${job.required_skills.length} required skills · ${job.min_experience_years}${job.max_experience_years ? `–${job.max_experience_years}` : '+'} years`} />
      <Tabs active={tab} onChange={setTab} tabs={[{ id: 'screening', label: 'Resume screening' }, { id: 'interviews', label: 'Interviews' }, { id: 'requirements', label: 'Requirements' }]} />
      {tab === 'screening' && <Screening job={job} />}
      {tab === 'interviews' && <JobInterviews jobId={job.id} />}
      {tab === 'requirements' && (
        <Card title="Edit requirements">
          {saved && <Alert tone="green" className="mb-4">Saved. Use “Re-score” on the screening tab to apply the new requirements to existing resumes.</Alert>}
          <JobForm initial={job} onSaved={onSaved} onCancel={() => setTab('screening')} />
        </Card>
      )}
    </>
  );
}
