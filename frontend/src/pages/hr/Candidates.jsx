import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Alert, Badge, Card, Empty, PageHeader, ScoreBadge, Spinner, StatusBadge, Table } from '../../components/ui';
import { results, useFetch } from '../../hooks/useFetch';

export default function Candidates() {
  const [f, setF] = useState({ search: '', job: '', status: '', min_score: '' });
  const jobs = useFetch('/jobs/', { params: { page_size: 100 } });
  const params = { page_size: 100, ...Object.fromEntries(Object.entries(f).filter(([, v]) => v)) };
  const { data, loading, error } = useFetch('/candidates/', { params });
  const rows = results(data);
  return (
    <>
      <PageHeader title="Candidates" subtitle="Every candidate across your jobs, with their AI-assisted resume assessment." />
      <Card pad={false}>
        <div className="flex flex-wrap gap-3 border-b border-gray-100 px-5 py-3">
          <input aria-label="Search candidates" className="input !w-60" placeholder="Search name or email…" value={f.search} onChange={(e) => setF({ ...f, search: e.target.value })} />
          <select aria-label="Job" className="input !w-56" value={f.job} onChange={(e) => setF({ ...f, job: e.target.value })}><option value="">All jobs</option>{results(jobs.data).map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}</select>
          <select aria-label="Status" className="input !w-44" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}><option value="">All statuses</option>{['screened', 'shortlisted', 'interview_invited', 'interviewing', 'interviewed', 'selected', 'rejected', 'on_hold'].map((s) => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}</select>
          <input aria-label="Minimum score" type="number" min="0" max="100" className="input !w-32" placeholder="Min. score" value={f.min_score} onChange={(e) => setF({ ...f, min_score: e.target.value })} />
        </div>
        {loading ? <Spinner /> : error ? <div className="p-5"><Alert>{error}</Alert></div> : (
          <Table rows={rows} rowKey={(r) => r.id} empty={<div className="p-5"><Empty title="No candidates found" /></div>} columns={[
            { key: 'full_name', header: 'Candidate', render: (r) => <Link className="font-semibold text-brand-700 hover:underline" to={`/candidates/${r.id}`}>{r.full_name}</Link> },
            { key: 'job_title', header: 'Job' },
            { key: 'match_score', header: 'Match', render: (r) => (r.parse_status === 'failed' ? <Badge tone="red">Unreadable</Badge> : <ScoreBadge value={r.match_score} />) },
            { key: 'skills', header: 'Matching skills', render: (r) => <span className="text-xs text-ink-600">{r.matching_skills.slice(0, 4).join(', ')}{r.matching_skills.length > 4 ? ` +${r.matching_skills.length - 4}` : ''}</span> },
            { key: 'status', header: 'Status', render: (r) => <StatusBadge status={r.status} /> },
          ]} />
        )}
      </Card>
    </>
  );
}
