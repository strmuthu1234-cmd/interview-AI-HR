import { useCallback, useEffect, useRef, useState } from 'react';

const pickMime = () => {
  if (typeof MediaRecorder === 'undefined') return '';
  return ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'].find((m) => MediaRecorder.isTypeSupported?.(m)) || '';
};

/**
 * Microphone recording with pause/resume, elapsed timer and a max-length guard.
 * status: idle | requesting | recording | paused | stopped | denied | unsupported | error
 * The recording is NEVER submitted automatically – the caller decides what happens next.
 */
export function useRecorder({ maxSeconds = 300 } = {}) {
  const supported = typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined';
  const [status, setStatus] = useState(supported ? 'idle' : 'unsupported');
  const [seconds, setSeconds] = useState(0);
  const [blob, setBlob] = useState(null);
  const [url, setUrl] = useState(null);
  const [error, setError] = useState('');
  const rec = useRef(null);
  const stream = useRef(null);
  const chunks = useRef([]);
  const timer = useRef(null);
  const elapsed = useRef(0);

  const stopTimer = () => { clearInterval(timer.current); timer.current = null; };
  const startTimer = (onTick) => {
    stopTimer();
    timer.current = setInterval(() => { elapsed.current += 1; setSeconds(elapsed.current); onTick?.(elapsed.current); }, 1000);
  };
  const release = () => { stream.current?.getTracks().forEach((t) => t.stop()); stream.current = null; };

  const stop = useCallback(() => {
    stopTimer();
    if (rec.current && rec.current.state !== 'inactive') rec.current.stop();
  }, []);

  const start = useCallback(async () => {
    if (!supported) return false;
    setError(''); setStatus('requesting');
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch (e) {
      const denied = e?.name === 'NotAllowedError' || e?.name === 'PermissionDeniedError';
      setStatus(denied ? 'denied' : 'error');
      setError(denied ? 'Microphone permission was denied. Allow it in your browser’s address bar, or answer by typing.' : e?.name === 'NotFoundError' ? 'No microphone was found on this device.' : 'The microphone could not be started.');
      return false;
    }
    chunks.current = []; elapsed.current = 0; setSeconds(0);
    if (url) URL.revokeObjectURL(url);
    setBlob(null); setUrl(null);
    const mime = pickMime();
    const r = new MediaRecorder(stream.current, mime ? { mimeType: mime } : undefined);
    rec.current = r;
    r.ondataavailable = (e) => { if (e.data?.size) chunks.current.push(e.data); };
    r.onstop = () => {
      const b = new Blob(chunks.current, { type: r.mimeType || mime || 'audio/webm' });
      setBlob(b); setUrl(URL.createObjectURL(b)); setStatus('stopped'); release();
    };
    r.onerror = () => { setStatus('error'); setError('Recording failed. Please try again or type your answer.'); stopTimer(); release(); };
    r.start(1000);
    setStatus('recording');
    startTimer((s) => { if (s >= maxSeconds) stop(); });
    return true;
  }, [supported, url, maxSeconds, stop]);

  const pause = useCallback(() => { if (rec.current?.state === 'recording') { rec.current.pause(); stopTimer(); setStatus('paused'); } }, []);
  const resume = useCallback(() => { if (rec.current?.state === 'paused') { rec.current.resume(); setStatus('recording'); startTimer((s) => { if (s >= maxSeconds) stop(); }); } }, [maxSeconds, stop]);
  const reset = useCallback(() => {
    stopTimer(); if (rec.current && rec.current.state !== 'inactive') { rec.current.onstop = null; rec.current.stop(); }
    release(); if (url) URL.revokeObjectURL(url);
    chunks.current = []; elapsed.current = 0; setSeconds(0); setBlob(null); setUrl(null); setError(''); setStatus(supported ? 'idle' : 'unsupported');
  }, [url, supported]);

  useEffect(() => () => { stopTimer(); release(); }, []);
  return { supported, status, seconds, blob, url, error, start, stop, pause, resume, reset };
}

/** Quick permission check used before the interview starts. Returns {ok, message}. */
export async function checkMicrophone() {
  if (!navigator.mediaDevices?.getUserMedia) return { ok: false, code: 'unsupported', message: 'This browser cannot record audio. You can still type your answers.' };
  try {
    const s = await navigator.mediaDevices.getUserMedia({ audio: true });
    s.getTracks().forEach((t) => t.stop());
    return { ok: true, message: 'Microphone is ready.' };
  } catch (e) {
    if (e?.name === 'NotAllowedError' || e?.name === 'PermissionDeniedError') return { ok: false, code: 'denied', message: 'Microphone access was blocked. Allow it in your browser settings, or answer by typing.' };
    if (e?.name === 'NotFoundError') return { ok: false, code: 'missing', message: 'No microphone was found.' };
    return { ok: false, code: 'error', message: 'The microphone could not be started.' };
  }
}
