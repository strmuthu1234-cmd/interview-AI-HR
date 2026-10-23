import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Alert, Badge, Card, Empty, PageHeader, ProgressBar, ScoreBadge, Spinner, StatusBadge, Table } from '../../components/ui';
import { results, useFetch } from '../../hooks/useFetch';
import { fmtDate } from '../../lib/format';

export default function Interviews() {
  const [status, setStatus] = useState('');
  const { data, loading, error } = useFetch('/interviews/', { params: { page_size: 100, ...(status ? { status } : {}) }, interval: 10000 });
  const rows = results(data);
  return (
    <>
      <PageHeader title="Interviews" subtitle="Review generated questions, send invitations and follow progress." />
      <Card pad={false}>
        <div className="flex gap-3 border-b border-gray-100 px-5 py-3">
          <select aria-label="Filter by status" className="input !w-60" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All interviews</option>
            {[['draft', 'Questions to review'], ['ready', 'Ready to invite'], ['in_progress', 'In progress'], ['completed', 'Completed'], ['generation_failed', 'Generation failed']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        {loading ? <Spinner /> : error ? <div className="p-5"><Alert>{error}</Alert></div> : (
          <Table rows={rows} rowKey={(r) => r.id} empty={<div className="p-5"><Empty title="No interviews yet">Approve a shortlist on a job to create interviews.</Empty></div>} columns={[
            { key: 'candidate_name', header: 'Candidate', render: (r) => <Link className="font-semibold text-brand-700 hover:underline" to={`/interviews/${r.id}`}>{r.candidate_name}</Link> },
            { key: 'job_title', header: 'Job' },
            { key: 'status', header: 'Status', render: (r) => <span className="flex items-center gap-2"><StatusBadge status={r.status} />{r.is_mock && <Badge tone="red">MOCK</Badge>}</span> },
            { key: 'progress', header: 'Progress', render: (r) => <div className="w-32"><ProgressBar value={r.answered} max={r.total} label="Interview progress" /><span className="text-xs text-ink-500">{r.answered}/{r.total}</span></div> },
            { key: 'final_score', header: 'Final', render: (r) => (r.final_score != null ? <ScoreBadge value={r.final_score} /> : '—') },
            { key: 'decision', header: 'HR decision', render: (r) => (r.decision ? <StatusBadge status={r.decision} /> : r.status === 'completed' ? <Badge tone="amber">Pending</Badge> : '—') },
            { key: 'created_at', header: 'Created', render: (r) => fmtDate(r.created_at) },
          ]} />
        )}
      </Card>
    </>
  );
}
