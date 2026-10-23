import { useCallback, useEffect, useRef, useState } from 'react';
import { errorCode, errorMessage, isNetworkError } from '../../api/client';
import { Alert, Badge, ProgressBar, Spinner } from '../../components/ui';
import { useRecorder } from '../../hooks/useRecorder';
import { useSpeaker, useSpeechRecognition } from '../../hooks/useSpeech';
import { fmtClock, newId, safeStorage } from '../../lib/format';

const SECTION = { general: 'Part 1 · Getting to know you', technical: 'Part 2 · Role-specific questions' };

/**
 * One question at a time. The server decides which question is active; this component only ever
 * receives (and can only ever answer) that one question. Nothing is submitted automatically.
 */
export default function InterviewRoom({ api, sessionId, info, consent, onFinished, onNotStarted }) {
  const [q, setQ] = useState(null);
  const [progress, setProgress] = useState(info.progress);
  const [allDone, setAllDone] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [banner, setBanner] = useState(null);
  const [text, setText] = useState('');
  const [mode, setMode] = useState(consent ? 'voice' : 'text');
  const [upload, setUpload] = useState({ status: 'idle' }); // idle | uploading | done | error
  const [skipAudio, setSkipAudio] = useState(false);
  const [speakOn, setSpeakOn] = useState(true);
  const submissionId = useRef(newId());
  const maxSeconds = info.settings?.max_answer_seconds || 300;

  const recorder = useRecorder({ maxSeconds });
  const speech = useSpeechRecognition(info.language);
  const speaker = useSpeaker(info.language);
  const useBrowserStt = (info.settings?.stt_provider || 'browser') === 'browser';

  const draftKey = (id) => `interview-draft:${sessionId}:${id}`;

  const loadQuestion = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/interviews/${sessionId}/question/`);
      setProgress(data.progress);
      if (data.done) { setAllDone(true); setQ(null); return; }
      const nq = data.question;
      setQ(nq);
      recorder.reset(); speech.stop(); speech.reset();
      submissionId.current = newId();
      setUpload(nq.pending_audio ? { status: 'done', recovered: true } : { status: 'idle' });
      setSkipAudio(false);
      setText(safeStorage.get(draftKey(nq.id)) || nq.pending_audio?.transcript || '');
      setBanner(null);
    } catch (e) {
      if (errorCode(e) === 'not_started') onNotStarted?.();
      else setBanner({ tone: 'red', text: isNetworkError(e) ? 'Could not reach the server. Your progress is saved – check your connection.' : errorMessage(e), retry: true });
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, sessionId]);

  useEffect(() => { loadQuestion(); }, [loadQuestion]);
  useEffect(() => { if (q && speakOn) speaker.speak(q.text); return () => speaker.cancel(); }, [q?.id]); // eslint-disable-line
  useEffect(() => { if (q) safeStorage.set(draftKey(q.id), text); }, [text]); // eslint-disable-line

  // live transcript from the browser while recording
  useEffect(() => { if (recorder.status === 'recording' || recorder.status === 'paused') setText(speech.text); }, [speech.text]); // eslint-disable-line

  const startRec = async () => {
    setBanner(null); speech.reset(); setText(''); setUpload({ status: 'idle' }); setSkipAudio(false);
    const ok = await recorder.start();
    if (ok && useBrowserStt && speech.supported) speech.start();
  };
  const stopRec = () => { speech.stop(); recorder.stop(); };
  const pauseRec = () => { speech.stop(); recorder.pause(); };
  const resumeRec = () => { recorder.resume(); if (useBrowserStt && speech.supported) speech.start(); };

  const uploadAudio = useCallback(async () => {
    if (!recorder.blob) return;
    setUpload({ status: 'uploading' });
    const fd = new FormData();
    fd.append('audio', recorder.blob, 'answer.webm');
    fd.append('duration', String(recorder.seconds));
    fd.append('transcript', text);
    try {
      const { data } = await api.post(`/interviews/${sessionId}/voice-upload/`, fd, { timeout: 120000 });
      if (data.transcription === 'server' && data.transcript) setText(data.transcript);
      setUpload({ status: 'done', transcription: data.transcription });
    } catch (e) {
      setUpload({ status: 'error', message: isNetworkError(e) ? 'Network error while saving your recording.' : errorMessage(e) });
    }
  }, [api, sessionId, recorder.blob, recorder.seconds, text]);

  // after the candidate stops recording, store it on the server (still NOT submitted as the answer)
  useEffect(() => { if (recorder.status === 'stopped' && recorder.blob && consent && upload.status === 'idle') uploadAudio(); }, [recorder.status, recorder.blob]); // eslint-disable-line

  const recording = recorder.status === 'recording' || recorder.status === 'paused';
  const needsAudioSaved = mode === 'voice' && recorder.blob && consent && !skipAudio && upload.status !== 'done';
  const canSubmit = !busy && !recording && text.trim().length > 0 && !needsAudioSaved && upload.status !== 'uploading';

  const submit = async (skip = false) => {
    if (!q) return;
    setBusy(true); setBanner(null);
    try {
      const { data } = await api.post(`/interviews/${sessionId}/answer/`, {
        question_id: q.id, text: skip ? '' : text.trim(), skip, input_mode: mode,
        client_submission_id: submissionId.current, transcript_source: upload.transcription === 'server' ? 'server_stt' : speech.text ? 'browser' : '',
      });
      safeStorage.remove(draftKey(q.id));
      setProgress(data.progress);
      await loadQuestion();
    } catch (e) {
      const code = errorCode(e);
      if (code === 'wrong_question' || code === 'already_answered') { await loadQuestion(); return; }
      setBanner({ tone: 'red', text: isNetworkError(e) ? 'Could not reach the server. Your answer is kept on this page – press Submit again when you are back online (it will not be duplicated).' : errorMessage(e) });
    } finally { setBusy(false); }
  };

  const finish = async () => {
    setBusy(true);
    try { await api.post(`/interviews/${sessionId}/complete/`); onFinished(); }
    catch (e) { setBanner({ tone: 'red', text: isNetworkError(e) ? 'Could not reach the server – please try again.' : errorMessage(e) }); }
    finally { setBusy(false); }
  };

  if (loading && !q && !allDone) return <Spinner label="Loading your question…" />;
  if (allDone) {
    return (
      <div className="card mx-auto max-w-xl p-8 text-center">
        <div className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-full bg-emerald-100 text-2xl">✓</div>
        <h2 className="text-xl font-bold text-ink-900">You have answered all 20 questions</h2>
        <p className="mt-2 text-sm text-ink-600">Press the button below to submit your interview. You will not be able to change your answers afterwards.</p>
        {banner && <Alert className="mt-4 text-left">{banner.text}</Alert>}
        <button className="btn-primary mt-6 w-full" disabled={busy} onClick={finish}>{busy ? 'Submitting…' : 'Submit interview'}</button>
      </div>
    );
  }
  if (!q) return banner ? <Alert>{banner.text} <button className="ml-2 font-semibold underline" onClick={loadQuestion}>Retry</button></Alert> : null;

  const pct = ((q.number - 1) / q.total) * 100;
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div className="card p-5">
        <div className="mb-2 flex items-center justify-between text-sm">
          <span className="font-semibold text-ink-900" data-testid="question-counter">Question {q.number} of {q.total}</span>
          <Badge tone="purple">{SECTION[q.section]}</Badge>
        </div>
        <ProgressBar value={pct} label="Interview progress" />
        <p className="mt-1 text-xs text-ink-500">{progress.answered} answered</p>
      </div>

      {banner && <Alert tone={banner.tone}>{banner.text} {banner.retry && <button className="ml-2 font-semibold underline" onClick={loadQuestion}>Retry</button>}</Alert>}

      <div className="card p-6">
        <div className="mb-3 flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-full bg-brand-700 text-sm font-bold text-white" aria-hidden="true">AI</div>
          <div><p className="text-sm font-semibold text-ink-900">AI interviewer</p><p className="text-xs text-ink-500">{speaker.speaking ? 'Speaking…' : 'Listening when you are ready'}</p></div>
          <div className="ml-auto flex gap-2">
            {speaker.supported && <button className="btn-secondary" onClick={() => speaker.speak(q.text)} aria-label="Read the question aloud again">🔊 Replay question</button>}
            {speaker.supported && <label className="flex items-center gap-1.5 text-xs text-ink-600"><input type="checkbox" className="accent-brand-700" checked={speakOn} onChange={(e) => { setSpeakOn(e.target.checked); if (!e.target.checked) speaker.cancel(); }} />Read aloud</label>}
          </div>
        </div>
        <p className="text-lg font-medium leading-relaxed text-ink-900" data-testid="question-text">{q.text}</p>
      </div>

      <div className="card p-6">
        <div role="tablist" aria-label="Answer method" className="mb-4 inline-flex rounded-xl bg-gray-100 p-1">
          {[['voice', '🎙 Voice'], ['text', '⌨ Type']].map(([m, l]) => (
            <button key={m} role="tab" aria-selected={mode === m} disabled={recording || (m === 'voice' && !recorder.supported && !speech.supported)} onClick={() => setMode(m)}
              className={`rounded-lg px-4 py-1.5 text-sm font-semibold transition disabled:opacity-40 ${mode === m ? 'bg-white text-brand-700 shadow-sm' : 'text-ink-600'}`}>{l}</button>
          ))}
        </div>

        {mode === 'voice' && (
          <div className="mb-4 space-y-3">
            {!consent && <Alert tone="blue">You chose not to have audio recorded. {speech.supported ? 'You can still dictate – only the text is kept.' : 'Please type your answer.'}</Alert>}
            {recorder.status === 'denied' && <Alert>{recorder.error}</Alert>}
            {recorder.status === 'unsupported' && consent && <Alert tone="amber">Audio recording is not supported in this browser. Please type your answer.</Alert>}
            {recorder.status === 'error' && <Alert>{recorder.error}</Alert>}
            <div className="flex flex-wrap items-center gap-2">
              {!recording && <button className="btn-primary" onClick={startRec} disabled={busy || (!recorder.supported && !speech.supported)}>{recorder.blob || text ? '● Record again' : '● Start recording'}</button>}
              {recorder.status === 'recording' && <button className="btn-secondary" onClick={pauseRec}>⏸ Pause</button>}
              {recorder.status === 'paused' && <button className="btn-secondary" onClick={resumeRec}>▶ Resume</button>}
              {recording && <button className="btn-danger" onClick={stopRec}>■ Stop</button>}
              <span aria-live="polite" className={`ml-1 inline-flex items-center gap-2 text-sm font-semibold ${recorder.status === 'recording' ? 'text-red-600' : 'text-ink-500'}`}>
                {recorder.status === 'recording' && <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-red-600" />}
                {recorder.status === 'recording' ? 'Recording' : recorder.status === 'paused' ? 'Paused' : recorder.status === 'requesting' ? 'Waiting for microphone permission…' : recorder.blob ? 'Recording ready' : 'Not recording'}
                {(recording || recorder.blob) && <span className="tabular-nums">{fmtClock(recorder.seconds)} / {fmtClock(maxSeconds)}</span>}
              </span>
            </div>
            {recorder.url && <audio controls src={recorder.url} className="w-full" aria-label="Replay your recorded answer" />}
            {upload.status === 'uploading' && <p className="text-sm text-ink-600">Saving your recording…</p>}
            {upload.status === 'error' && (
              <Alert tone="amber" title="Your recording could not be saved">{upload.message}
                <div className="mt-2 flex flex-wrap gap-2"><button className="btn-secondary" onClick={uploadAudio}>Retry upload</button><button className="btn-ghost" onClick={() => { setSkipAudio(true); setUpload({ status: 'idle' }); }}>Continue with text only</button></div>
              </Alert>
            )}
            {upload.status === 'done' && recorder.blob && <p className="text-sm text-emerald-700">✓ Recording saved. Review the transcript below, then submit.</p>}
            {q.pending_audio && !recorder.blob && <p className="text-sm text-emerald-700">✓ A recording from before you reloaded is saved. Review the transcript and submit, or record again.</p>}
            {speech.listening && speech.interim && <p className="text-sm italic text-ink-500">{speech.interim}</p>}
          </div>
        )}

        <label htmlFor="answer-text" className="label">{mode === 'voice' ? 'Transcript – check and correct before submitting' : 'Your answer'}</label>
        <textarea id="answer-text" className="input min-h-[150px] text-base leading-relaxed" value={text} disabled={busy || recording} maxLength={8000}
          onChange={(e) => setText(e.target.value)} placeholder={mode === 'voice' ? 'Your transcript appears here after you speak. You can edit it.' : 'Type your answer here…'} />
        <p className="mt-1 text-right text-xs text-ink-400">{text.length}/8000</p>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <button className="btn-ghost" disabled={busy || recording} onClick={() => window.confirm('Skip this question? It will be marked as unanswered and cannot be revisited.') && submit(true)}>I can’t answer this question</button>
          <button className="btn-primary min-w-[10rem]" disabled={!canSubmit} onClick={() => submit(false)}>{busy ? 'Submitting…' : q.number === q.total ? 'Submit final answer' : 'Submit answer'}</button>
        </div>
        <p className="mt-3 text-xs text-ink-500">The next question appears only after you submit. Pauses or silence never move the interview forward. If you lose connection, reopen your link and continue where you left off.</p>
      </div>
    </div>
  );
}
