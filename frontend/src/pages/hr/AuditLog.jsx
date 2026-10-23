import { useState } from 'react';
import { Alert, Badge, Card, Empty, PageHeader, Spinner, Table } from '../../components/ui';
import { results, useFetch } from '../../hooks/useFetch';
import { fmtDate } from '../../lib/format';

export default function AuditLog() {
  const [q, setQ] = useState('');
  const { data, loading, error } = useFetch('/audit-logs/', { params: { page_size: 100, ...(q ? { search: q } : {}) } });
  return (
    <>
      <PageHeader title="Audit log" subtitle="Append-only record of sensitive actions: logins, decisions, exports, recordings accessed." />
      <Card pad={false}>
        <div className="border-b border-gray-100 px-5 py-3"><input aria-label="Search audit log" className="input !w-72" placeholder="Search action or entity…" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        {loading ? <Spinner /> : error ? <div className="p-5"><Alert>{error}</Alert></div> : (
          <Table rows={results(data)} rowKey={(r) => r.id} empty={<div className="p-5"><Empty title="No entries" /></div>} columns={[
            { key: 'created_at', header: 'When', render: (r) => fmtDate(r.created_at) },
            { key: 'actor_name', header: 'Actor', render: (r) => r.actor_name || '—' },
            { key: 'action', header: 'Action', render: (r) => <Badge tone="purple">{r.action}</Badge> },
            { key: 'entity_type', header: 'Entity', render: (r) => `${r.entity_type} ${r.entity_id ? r.entity_id.slice(0, 8) : ''}` },
            { key: 'metadata', header: 'Details', render: (r) => <code className="text-xs text-ink-500">{Object.keys(r.metadata).length ? JSON.stringify(r.metadata).slice(0, 90) : ''}</code> },
            { key: 'ip_address', header: 'IP' },
          ]} />
        )}
      </Card>
    </>
  );
}
