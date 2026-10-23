import { useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { errorMessage } from '../../api/client';
import { useAuth } from '../../auth/AuthContext';
import { Alert } from '../../components/ui';

export default function Login() {
  const { user, login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [form, setForm] = useState({ username: '', password: '' });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to={loc.state?.from || '/'} replace />;

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await login(form.username.trim(), form.password);
      nav(loc.state?.from || '/', { replace: true });
    } catch (err) {
      setError(err?.response?.status === 401 ? 'Incorrect username or password.' : errorMessage(err));
    } finally { setBusy(false); }
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="hidden bg-gradient-to-br from-brand-800 via-brand-700 to-brand-900 p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div className="flex items-center gap-3"><div className="grid h-10 w-10 place-items-center rounded-xl bg-white/15 font-bold">HR</div><span className="font-semibold">AI Recruitment &amp; Interview System</span></div>
        <div>
          <h1 className="max-w-md text-4xl font-bold leading-tight">Screen faster. Interview fairly. Decide with evidence.</h1>
          <p className="mt-4 max-w-md text-brand-100">Resume screening, structured AI interviews and evidence-based reports – with a human making every final decision.</p>
        </div>
        <p className="text-sm text-brand-200">AI provides decision support only.</p>
      </div>
      <div className="flex items-center justify-center p-6">
        <form onSubmit={submit} className="w-full max-w-sm space-y-5" aria-label="Sign in">
          <div><h2 className="text-2xl font-bold text-ink-900">Sign in</h2><p className="mt-1 text-sm text-ink-500">HR managers and administrators</p></div>
          {error && <Alert>{error}</Alert>}
          <div><label className="label" htmlFor="username">Username</label><input id="username" className="input" autoComplete="username" required value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></div>
          <div><label className="label" htmlFor="password">Password</label><input id="password" type="password" className="input" autoComplete="current-password" required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></div>
          <button className="btn-primary w-full" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
          <p className="text-center text-xs text-ink-500">Candidates: open the personal interview link you received by email.</p>
        </form>
      </div>
    </div>
  );
}
