import { useCallback, useEffect, useRef, useState } from 'react';

const LANG = { en: 'en-US', ta: 'ta-IN' };
const getRecognition = () => (typeof window !== 'undefined' ? window.SpeechRecognition || window.webkitSpeechRecognition : undefined);

/** Text-to-speech for the AI interviewer (browser speechSynthesis). Silent no-op when unsupported. */
export function useSpeaker(lang = 'en') {
  const supported = typeof window !== 'undefined' && 'speechSynthesis' in window && typeof SpeechSynthesisUtterance !== 'undefined';
  const [speaking, setSpeaking] = useState(false);
  const cancel = useCallback(() => { if (supported) window.speechSynthesis.cancel(); setSpeaking(false); }, [supported]);
  const speak = useCallback((text) => {
    if (!supported || !text) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = LANG[lang] || 'en-US';
    u.rate = 0.95;
    u.onstart = () => setSpeaking(true);
    u.onend = () => setSpeaking(false);
    u.onerror = () => setSpeaking(false);
    window.speechSynthesis.speak(u);
  }, [supported, lang]);
  useEffect(() => cancel, [cancel]);
  return { supported, speaking, speak, cancel };
}

/**
 * Browser speech-to-text (live transcript while recording).
 * Note: many browsers stream audio to their vendor's servers for recognition – disclosed to the candidate.
 */
export function useSpeechRecognition(lang = 'en') {
  const Ctor = getRecognition();
  const supported = !!Ctor;
  const [finalText, setFinalText] = useState('');
  const [interim, setInterim] = useState('');
  const [listening, setListening] = useState(false);
  const ref = useRef(null);
  const wantOn = useRef(false);

  const start = useCallback(() => {
    if (!Ctor) return;
    wantOn.current = true;
    const r = new Ctor();
    r.lang = LANG[lang] || 'en-US';
    r.continuous = true;
    r.interimResults = true;
    r.onresult = (e) => {
      let fin = '', inter = '';
      for (let i = e.resultIndex; i < e.results.length; i += 1) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) fin += t; else inter += t;
      }
      if (fin) setFinalText((p) => `${p}${p && !p.endsWith(' ') ? ' ' : ''}${fin.trim()}`);
      setInterim(inter);
    };
    r.onend = () => { setInterim(''); if (wantOn.current) { try { r.start(); } catch { setListening(false); } } else setListening(false); };
    r.onerror = (e) => { if (e.error === 'not-allowed' || e.error === 'service-not-allowed') { wantOn.current = false; setListening(false); } };
    try { r.start(); ref.current = r; setListening(true); } catch { setListening(false); }
  }, [Ctor, lang]);

  const stop = useCallback(() => { wantOn.current = false; try { ref.current?.stop(); } catch { /* ignore */ } setListening(false); setInterim(''); }, []);
  const reset = useCallback(() => { setFinalText(''); setInterim(''); }, []);
  useEffect(() => () => { wantOn.current = false; try { ref.current?.abort(); } catch { /* ignore */ } }, []);
  return { supported, listening, text: finalText, interim, setText: setFinalText, start, stop, reset };
}
