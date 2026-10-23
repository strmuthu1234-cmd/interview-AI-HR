import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { candidateApi, errorMessage } from '../../api/client';
import { Alert, Spinner } from '../../components/ui';
import { checkMicrophone } from '../../hooks/useRecorder';
import InterviewRoom from './InterviewRoom';

function Shell({ children, company }) {
  return (
    <div className="min-h-screen bg-gradient-to-b from-brand-50/60 to-white">
      <header className="border-b border-gray-100 bg-white/80 px-4 py-3 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center gap-3"><div className="grid h-8 w-8 place-items-center rounded-lg bg-brand-700 text-xs font-bold text-white">HR</div><span className="text-sm font-semibold text-ink-900">{company ? `${company} · Online interview` : 'Online interview'}</span></div>
      </header>
      <main className="px-4 py-8">{children}</main>
    </div>
  );
}

export function Welcome({ info, onStart }) {
  const [accepted, setAccepted] = useState(false);
  const [consent, setConsent] = useState(null); // null = not chosen yet
  const [mic, setMic] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const test = async () => { setMic({ message: 'Checking microphone…' }); setMic(await checkMicrophone()); };
  const start = async () => { setBusy(true); setErr(''); try { await onStart(consent === true); } catch (e) { setErr(errorMessage(e)); setBusy(false); } };

  return (
    <div className="card mx-auto max-w-2xl p-6 sm:p-8">
      <h1 className="text-2xl font-bold text-ink-900">Hello{info.candidate_first_name ? `, ${info.candidate_first_name}` : ''} 👋</h1>
      <p className="mt-1 text-ink-600">Welcome to your interview for <b>{info.job_title}</b> at <b>{info.company}</b>. It takes about {info.duration_minutes} minutes.</p>
      <h2 className="mt-6 text-sm font-semibold uppercase tracking-wide text-ink-500">Before you begin</h2>
      <ul className="mt-2 space-y-2 text-sm text-ink-700">{info.instructions.map((i) => <li key={i} className="flex gap-2"><span className="text-brand-600">•</span>{i}</li>)}</ul>

      <fieldset className="mt-6 rounded-xl border border-gray-200 p-4">
        <legend className="px-1 text-sm font-semibold text-ink-900">Audio recording consent</legend>
        <p className="mb-3 text-xs text-ink-500">If you agree, your spoken answers are stored securely and may be replayed by the hiring team. Browser speech-to-text may send audio to your browser provider for transcription. You can decline and type instead.</p>
        <label className="mb-2 flex items-start gap-2 text-sm"><input type="radio" name="consent" className="mt-1 accent-brand-700" checked={consent === true} onChange={() => setConsent(true)} />I agree to my voice answers being recorded and stored.</label>
        <label className="flex items-start gap-2 text-sm"><input type="radio" name="consent" className="mt-1 accent-brand-700" checked={consent === false} onChange={() => setConsent(false)} />I do not want audio stored (I will type or dictate text only).</label>
      </fieldset>

      <div className="mt-4 rounded-xl border border-gray-200 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><p className="text-sm font-semibold text-ink-900">Microphone check</p><p className="text-xs text-ink-500">Optional, but recommended for voice answers.</p></div>
          <button className="btn-secondary" onClick={test}>Test microphone</button>
        </div>
        {mic && <p role="status" className={`mt-2 text-sm ${mic.ok ? 'text-emerald-700' : mic.ok === false ? 'text-red-700' : 'text-ink-500'}`}>{mic.ok ? '✓ ' : mic.ok === false ? '✕ ' : ''}{mic.message}</p>}
      </div>

      <label className="mt-5 flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1 h-4 w-4 accent-brand-700" checked={accepted} onChange={(e) => setAccepted(e.target.checked)} />I have read and accept the interview instructions.</label>
      {err && <Alert className="mt-3">{err}</Alert>}
      <button className="btn-primary mt-5 w-full" disabled={!accepted || consent === null || busy} onClick={start}>{busy ? 'Starting…' : 'Start interview'}</button>
      {consent === null && <p className="mt-2 text-center text-xs text-ink-500">Please choose a recording option to continue.</p>}
    </div>
  );
}

export default function InterviewEntry() {
  const { token } = useParams();
  const api = useMemo(() => candidateApi(token), [token]);
  const [state, setState] = useState({ step: 'loading' });

  const load = useCallback(async () => {
    try {
      const { data } = await api.post('/interviews/access/');
      if (data.progress.completed) setState({ step: 'done', info: data });
      else if (!data.available) setState({ step: 'unavailable', info: data });
      else if (data.progress.instructions_accepted) setState({ step: 'room', info: data, consent: data.progress.recording_consent });
      else setState({ step: 'welcome', info: data });
    } catch (e) {
      setState({ step: 'error', message: e.response?.status === 401 ? 'This interview link is invalid, has expired, or was withdrawn. Please contact the hiring team for a new link.' : errorMessage(e), network: !e.response });
    }
  }, [api]);
  useEffect(() => { load(); }, [load]);

  const start = async (consent) => {
    await api.post(`/interviews/${state.info.session_id}/accept-instructions/`, { accept: true, recording_consent: consent });
    setState({ step: 'room', info: state.info, consent });
  };

  const company = state.info?.company;
  return (
    <Shell company={company}>
      {state.step === 'loading' && <Spinner label="Opening your interview…" />}
      {state.step === 'error' && <div className="mx-auto max-w-lg"><Alert title="We couldn’t open your interview">{state.message}{state.network && <button className="ml-2 font-semibold underline" onClick={load}>Try again</button>}</Alert></div>}
      {state.step === 'unavailable' && <div className="mx-auto max-w-lg"><Alert tone="amber" title="Your interview isn’t ready yet">The hiring team is still preparing it. Please try this link again later.</Alert></div>}
      {state.step === 'welcome' && <Welcome info={state.info} onStart={start} />}
      {state.step === 'room' && <InterviewRoom api={api} sessionId={state.info.session_id} info={state.info} consent={state.consent} onFinished={() => setState({ step: 'done', info: state.info })} onNotStarted={() => setState({ step: 'welcome', info: state.info })} />}
      {state.step === 'done' && (
        <div className="card mx-auto max-w-xl p-8 text-center">
          <div className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-full bg-emerald-100 text-2xl">✓</div>
          <h1 className="text-2xl font-bold text-ink-900">Interview submitted</h1>
          <p className="mt-2 text-ink-600">Thank you{state.info.candidate_first_name ? `, ${state.info.candidate_first_name}` : ''}! Your answers have been received by {state.info.company}. The hiring team will review them and contact you about next steps. You can close this window.</p>
        </div>
      )}
    </Shell>
  );
}
