import { useEffect, useState } from 'react';
import { api, errorMessage } from '../../api/client';
import { useAuth } from '../../auth/AuthContext';
import { Alert, Badge, Card, Field, PageHeader, Spinner } from '../../components/ui';
import { useFetch } from '../../hooks/useFetch';

const LABELS = {
  required_skills: 'Required technical skills', experience: 'Relevant experience', projects: 'Project relevance', preferred_skills: 'Preferred skills', qualifications: 'Job-related qualifications',
  resume: 'Resume match', general: 'General interview', technical: 'Technical interview',
  correctness: 'Technical / factual correctness', relevance: 'Relevance to question', reasoning: 'Explanation & reasoning', examples: 'Practical examples', job_alignment: 'Job alignment',
};

function Weights({ title, value, onChange, disabled }) {
  const total = Object.values(value).reduce((a, b) => a + Number(b || 0), 0);
  return (
    <div>
      <div className="mb-2 flex items-center justify-between"><h3 className="text-sm font-semibold text-ink-900">{title}</h3><Badge tone={Math.abs(total - 100) < 0.01 ? 'green' : 'red'}>Total {total}%</Badge></div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {Object.entries(value).map(([k, v]) => (
          <Field key={k} label={LABELS[k] || k}>{(id) => <input id={id} type="number" min="0" max="100" disabled={disabled} className="input" value={v} onChange={(e) => onChange({ ...value, [k]: e.target.value === '' ? '' : Number(e.target.value) })} />}</Field>
        ))}
      </div>
    </div>
  );
}

export default function Settings() {
  const { isAdmin } = useAuth();
  const { data, loading, error, reload } = useFetch('/settings/');
  const [s, setS] = useState(null);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (data) setS(JSON.parse(JSON.stringify(data.settings))); }, [data]);
  if (loading || !s) return error ? <Alert>{error}</Alert> : <Spinner />;
  const ai = data.ai_status;
  const ro = !isAdmin;
  const up = (path, v) => setS((cur) => { const n = JSON.parse(JSON.stringify(cur)); let o = n; path.slice(0, -1).forEach((k) => { o = o[k]; }); o[path.at(-1)] = v; return n; });
  const save = async () => {
    setBusy(true); setMsg(null);
    try { await api.patch('/settings/', { settings: s }); setMsg({ tone: 'green', text: 'Settings saved. New weights apply to future scoring; use “Re-score” on a job to re-apply them to existing resumes.' }); reload(); }
    catch (e) { setMsg({ tone: 'red', text: errorMessage(e) }); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader title="Settings" subtitle={ro ? 'Read-only. Ask an administrator to change these settings.' : 'Scoring rubrics, AI provider, voice and data retention.'}
        actions={!ro && <button className="btn-primary" onClick={save} disabled={busy}>{busy ? 'Saving…' : 'Save settings'}</button>} />
      {msg && <Alert tone={msg.tone} className="mb-4">{msg.text}</Alert>}
      <div className="space-y-6">
        <Card title="AI provider">
          {ai.configured && !ai.is_mock && <Alert tone="green" className="mb-4">Connected: <b>{ai.provider}</b> · model <b>{ai.model}</b></Alert>}
          {ai.is_mock && <Alert tone="red" title="Mock testing mode" className="mb-4">Questions and evaluations come from a clearly-labelled keyword heuristic. Use it only to test the workflow – never for real decisions.</Alert>}
          {!ai.configured && <Alert tone="amber" title="No AI provider configured" className="mb-4">{ai.message}</Alert>}
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Provider">{(id) => <select id={id} disabled={ro} className="input" value={s.ai.provider} onChange={(e) => up(['ai', 'provider'], e.target.value)}><option value="">Use server default (AI_PROVIDER)</option><option value="openai">OpenAI</option><option value="anthropic">Anthropic Claude</option><option value="mock">Mock testing mode (not real)</option></select>}</Field>
            <Field label="Model" hint="Leave empty for the provider default.">{(id) => <input id={id} disabled={ro} className="input" value={s.ai.model} onChange={(e) => up(['ai', 'model'], e.target.value)} placeholder="e.g. claude-sonnet-5-5" />}</Field>
            <div><p className="label">API keys (server environment)</p><div className="flex gap-2 pt-2"><Badge tone={ai.keys_present.openai ? 'green' : 'gray'}>OpenAI {ai.keys_present.openai ? 'set' : 'not set'}</Badge><Badge tone={ai.keys_present.anthropic ? 'green' : 'gray'}>Anthropic {ai.keys_present.anthropic ? 'set' : 'not set'}</Badge></div><p className="mt-1 text-xs text-ink-500">Keys are never entered or stored here.</p></div>
          </div>
          <label className="mt-4 flex items-start gap-3 rounded-xl bg-gray-50 p-3 text-sm"><input type="checkbox" disabled={ro} className="mt-0.5 h-4 w-4 accent-brand-700" checked={s.ai.allow_resume_sharing} onChange={(e) => up(['ai', 'allow_resume_sharing'], e.target.checked)} />
            <span><b>Allow AI processing of resume content.</b> When off, no resume content is sent to an external provider: screening stays rule-based and personalised questions cannot be generated by a real provider. When on, only de-identified text (no name, email, phone, links or protected attributes) is sent.</span></label>
        </Card>
        <Card title="Resume screening rubric"><Weights title="Category weights" value={s.screening_weights} onChange={(v) => up(['screening_weights'], v)} disabled={ro} /></Card>
        <Card title="Final assessment formula"><Weights title="Normalised to 100 before weighting" value={s.final_weights} onChange={(v) => up(['final_weights'], v)} disabled={ro} /></Card>
        <Card title="Answer evaluation rubrics"><div className="space-y-6"><Weights title="Technical questions" value={s.answer_weights.technical} onChange={(v) => up(['answer_weights', 'technical'], v)} disabled={ro} /><Weights title="Behavioral / general questions" value={s.answer_weights.behavioral} onChange={(v) => up(['answer_weights', 'behavioral'], v)} disabled={ro} /></div></Card>
        <Card title="Voice & interview">
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Speech-to-text">{(id) => <select id={id} disabled={ro} className="input" value={s.voice.stt_provider} onChange={(e) => up(['voice', 'stt_provider'], e.target.value)}><option value="browser">Browser (default)</option><option value="server" disabled={!ai.server_stt_available}>Server (OpenAI){ai.server_stt_available ? '' : ' – key missing'}</option></select>}</Field>
            <Field label="Max answer length (seconds)">{(id) => <input id={id} type="number" min="30" max="900" disabled={ro} className="input" value={s.interview.max_answer_seconds} onChange={(e) => up(['interview', 'max_answer_seconds'], Number(e.target.value))} />}</Field>
            <Field label="Invitation validity (days)">{(id) => <input id={id} type="number" min="1" max="60" disabled={ro} className="input" value={s.interview.invite_expiry_days} onChange={(e) => up(['interview', 'invite_expiry_days'], Number(e.target.value))} />}</Field>
          </div>
          <label className="mt-4 flex items-center gap-2 text-sm"><input type="checkbox" disabled={ro} className="h-4 w-4 accent-brand-700" checked={s.interview.reveal_results_to_candidate} onChange={(e) => up(['interview', 'reveal_results_to_candidate'], e.target.checked)} />Show per-answer feedback to all candidates (off recommended; can also be enabled per interview)</label>
        </Card>
        <Card title="Data retention">
          <div className="grid gap-4 sm:grid-cols-3">
            {[['audio_days', 'Audio recordings (days)'], ['resume_days', 'Resume files & text (days)'], ['interview_days', 'Completed interviews (days)']].map(([k, l]) => (
              <Field key={k} label={l}>{(id) => <input id={id} type="number" min="1" disabled={ro} className="input" value={s.retention[k]} onChange={(e) => up(['retention', k], Number(e.target.value))} />}</Field>))}
          </div>
          <p className="mt-2 text-xs text-ink-500">A daily background job permanently deletes data older than these limits.</p>
        </Card>
      </div>
    </>
  );
}
