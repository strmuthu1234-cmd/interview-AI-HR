import { Link } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Alert, Card, Empty, PageHeader, Spinner, Stat, StatusBadge, Table } from '../../components/ui';
import { results, useFetch } from '../../hooks/useFetch';
import { STATUS_LABEL, fmtDate } from '../../lib/format';

const PURPLES = ['#ddd6fe', '#a78bfa', '#7c3aed', '#4c1d95'];

export default function Dashboard() {
  const stats = useFetch('/dashboard/stats/', { interval: 15000 });
  const pending = useFetch('/interviews/', { params: { status: 'completed', page_size: 100 } });
  const settings = useFetch('/settings/');
  if (stats.loading) return <Spinner />;
  const s = stats.data;
  if (!s) return <Alert>{stats.error}</Alert>;
  const byStatus = Object.entries(s.candidates_by_status || {}).map(([k, v]) => ({ name: STATUS_LABEL[k] || k, value: v }));
  const needsReview = results(pending.data).filter((x) => !x.decision);
  const ai = settings.data?.ai_status;

  return (
    <>
      <PageHeader title="Dashboard" subtitle="Hiring pipeline at a glance." />
      {ai && !ai.configured && (
        <Alert tone="amber" title="AI provider not configured" className="mb-6">
          Resume screening works without AI (deterministic scoring), but interview questions and answer evaluation need a provider. {ai.message}{' '}
          <Link className="font-semibold underline" to="/settings">Open settings</Link>
        </Alert>
      )}
      {ai?.is_mock && <Alert tone="red" title="Mock testing mode is ON" className="mb-6">Interview questions and evaluations are produced by a keyword heuristic for testing only. Do not use them for real hiring decisions.</Alert>}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Total jobs" value={s.total_jobs} />
        <Stat label="Resumes uploaded" value={s.total_resumes} />
        <Stat label="Screened candidates" value={s.screened_candidates} />
        <Stat label="Proposed shortlist" value={s.proposed_shortlist} hint="awaiting your approval" accent />
        <Stat label="Interviews scheduled" value={s.interviews_scheduled} />
        <Stat label="Interviews completed" value={s.interviews_completed} />
        <Stat label="Pending HR reviews" value={s.pending_hr_reviews} hint="completed, no decision yet" accent />
      </div>
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card title="Resume match score distribution">
          <div className="h-64" role="img" aria-label="Bar chart of resume match scores by range">
            <ResponsiveContainer>
              <BarChart data={s.score_distribution}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="range" /><YAxis allowDecimals={false} /><Tooltip />
                <Bar dataKey="count" radius={[8, 8, 0, 0]}>{s.score_distribution.map((_, i) => <Cell key={i} fill={PURPLES[i]} />)}</Bar></BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card title="Candidates by stage">
          {byStatus.length ? (
            <div className="h-64" role="img" aria-label="Bar chart of candidates by pipeline stage">
              <ResponsiveContainer><BarChart data={byStatus} layout="vertical" margin={{ left: 30 }}><CartesianGrid strokeDasharray="3 3" horizontal={false} /><XAxis type="number" allowDecimals={false} /><YAxis type="category" dataKey="name" width={110} /><Tooltip /><Bar dataKey="value" fill="#6d28d9" radius={[0, 8, 8, 0]} /></BarChart></ResponsiveContainer>
            </div>
          ) : <Empty title="No candidates yet">Create a job and upload resumes to get started.</Empty>}
        </Card>
      </div>
      <Card title="Awaiting your decision" className="mt-6" pad={false}>
        <Table rows={needsReview} rowKey={(r) => r.id} columns={[
          { key: 'candidate_name', header: 'Candidate', render: (r) => <Link className="font-semibold text-brand-700 hover:underline" to={`/reports/${r.id}`}>{r.candidate_name}</Link> },
          { key: 'job_title', header: 'Job' },
          { key: 'final_score', header: 'Final score', render: (r) => r.final_score ?? '—' },
          { key: 'completed_at', header: 'Completed', render: (r) => fmtDate(r.completed_at) },
          { key: 'status', header: '', render: (r) => <StatusBadge status={r.status} /> },
        ]} empty={<div className="p-5"><Empty title="Nothing waiting">Completed interviews without a decision appear here.</Empty></div>} />
      </Card>
    </>
  );
}
