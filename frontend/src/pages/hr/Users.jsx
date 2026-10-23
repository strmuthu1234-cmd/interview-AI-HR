import { useState } from 'react';
import { api, errorMessage } from '../../api/client';
import { Alert, Badge, Card, Field, Modal, PageHeader, Spinner, Table } from '../../components/ui';
import { results, useFetch } from '../../hooks/useFetch';
import { fmtDate } from '../../lib/format';

export default function Users() {
  const { data, loading, error, reload } = useFetch('/users/', { params: { page_size: 200 } });
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ username: '', email: '', first_name: '', last_name: '', role: 'hr_manager', password: '' });
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);

  const create = async (e) => {
    e.preventDefault(); setErr(null);
    try { await api.post('/users/', f); setOpen(false); setF({ username: '', email: '', first_name: '', last_name: '', role: 'hr_manager', password: '' }); reload(); }
    catch (ex) { setErr(ex.response?.data || { detail: errorMessage(ex) }); }
  };
  const patch = async (u, body) => { setMsg(null); try { await api.patch(`/users/${u.id}/`, body); reload(); } catch (ex) { setMsg(errorMessage(ex)); } };
  const fe = (k) => (err?.[k] ? [].concat(err[k]).join(' ') : undefined);

  return (
    <>
      <PageHeader title="Users" subtitle="HR managers and administrators in your organisation." actions={<button className="btn-primary" onClick={() => setOpen(true)}>+ Add user</button>} />
      {msg && <Alert className="mb-4">{msg}</Alert>}
      <Card pad={false}>
        {loading ? <Spinner /> : error ? <div className="p-5"><Alert>{error}</Alert></div> : (
          <Table rows={results(data)} rowKey={(u) => u.id} columns={[
            { key: 'username', header: 'User', render: (u) => <div><p className="font-semibold">{u.first_name} {u.last_name} <span className="font-normal text-ink-500">@{u.username}</span></p><p className="text-xs text-ink-500">{u.email}</p></div> },
            { key: 'role', header: 'Role', render: (u) => <select aria-label={`Role for ${u.username}`} className="input !w-40" value={u.role} onChange={(e) => patch(u, { role: e.target.value })}><option value="hr_manager">HR manager</option><option value="admin">Admin</option></select> },
            { key: 'is_active', header: 'Status', render: (u) => <Badge tone={u.is_active ? 'green' : 'gray'}>{u.is_active ? 'Active' : 'Disabled'}</Badge> },
            { key: 'last_login', header: 'Last login', render: (u) => fmtDate(u.last_login) },
            { key: 'a', header: '', render: (u) => <button className="btn-secondary" onClick={() => patch(u, { is_active: !u.is_active })}>{u.is_active ? 'Disable' : 'Enable'}</button> },
          ]} />
        )}
      </Card>
      <Modal open={open} onClose={() => setOpen(false)} title="Add user">
        <form onSubmit={create} className="space-y-3">
          {err?.detail && <Alert>{err.detail}</Alert>}
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Username" error={fe('username')}>{(id) => <input id={id} required className="input" value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} />}</Field>
            <Field label="Email" error={fe('email')}>{(id) => <input id={id} type="email" required className="input" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />}</Field>
            <Field label="First name">{(id) => <input id={id} className="input" value={f.first_name} onChange={(e) => setF({ ...f, first_name: e.target.value })} />}</Field>
            <Field label="Last name">{(id) => <input id={id} className="input" value={f.last_name} onChange={(e) => setF({ ...f, last_name: e.target.value })} />}</Field>
          </div>
          <Field label="Role">{(id) => <select id={id} className="input" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}><option value="hr_manager">HR manager</option><option value="admin">Admin</option></select>}</Field>
          <Field label="Initial password" hint="Min. 10 characters, not common." error={fe('password')}>{(id) => <input id={id} type="password" required className="input" autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />}</Field>
          <div className="flex justify-end gap-2"><button type="button" className="btn-secondary" onClick={() => setOpen(false)}>Cancel</button><button className="btn-primary">Create user</button></div>
        </form>
      </Modal>
    </>
  );
}
