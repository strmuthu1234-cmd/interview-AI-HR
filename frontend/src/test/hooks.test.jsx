import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { checkMicrophone, useRecorder } from '../hooks/useRecorder';

class FakeRecorder {
  static isTypeSupported() { return true; }
  constructor(stream) { this.stream = stream; this.state = 'inactive'; this.mimeType = 'audio/webm'; FakeRecorder.last = this; }
  start() { this.state = 'recording'; this.ondataavailable?.({ data: new Blob(['abc'], { type: 'audio/webm' }) }); }
  pause() { this.state = 'paused'; }
  resume() { this.state = 'recording'; }
  stop() { this.state = 'inactive'; this.onstop?.(); }
}

const track = { stop: vi.fn() };
const stream = { getTracks: () => [track] };

describe('useRecorder', () => {
  beforeEach(() => {
    vi.stubGlobal('MediaRecorder', FakeRecorder);
    Object.defineProperty(navigator, 'mediaDevices', { value: { getUserMedia: vi.fn().mockResolvedValue(stream) }, configurable: true });
  });
  afterEach(() => { vi.unstubAllGlobals(); track.stop.mockClear(); });

  it('records, pauses, resumes and stops without submitting anything', async () => {
    const { result } = renderHook(() => useRecorder({ maxSeconds: 60 }));
    expect(result.current.status).toBe('idle');
    await act(async () => { await result.current.start(); });
    expect(result.current.status).toBe('recording');
    act(() => result.current.pause());
    expect(result.current.status).toBe('paused');
    act(() => result.current.resume());
    expect(result.current.status).toBe('recording');
    act(() => result.current.stop());
    await waitFor(() => expect(result.current.status).toBe('stopped'));
    expect(result.current.blob).toBeInstanceOf(Blob);
    expect(result.current.url).toBeTruthy();
    expect(track.stop).toHaveBeenCalled(); // microphone released
  });

  it('reports a clear state when permission is denied', async () => {
    navigator.mediaDevices.getUserMedia.mockRejectedValueOnce(Object.assign(new Error('x'), { name: 'NotAllowedError' }));
    const { result } = renderHook(() => useRecorder());
    await act(async () => { expect(await result.current.start()).toBe(false); });
    expect(result.current.status).toBe('denied');
    expect(result.current.error).toMatch(/permission was denied/i);
  });

  it('auto-stops at the maximum length but still waits for the candidate to submit', async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useRecorder({ maxSeconds: 3 }));
    await act(async () => { await result.current.start(); });
    await act(async () => { vi.advanceTimersByTime(3100); });
    expect(result.current.status).toBe('stopped');
    expect(result.current.seconds).toBe(3);
    vi.useRealTimers();
  });

  it('reset discards the recording', async () => {
    const { result } = renderHook(() => useRecorder());
    await act(async () => { await result.current.start(); });
    act(() => result.current.stop());
    await waitFor(() => expect(result.current.blob).toBeTruthy());
    act(() => result.current.reset());
    expect(result.current.blob).toBeNull();
    expect(result.current.status).toBe('idle');
  });

  it('checkMicrophone maps errors to messages', async () => {
    expect((await checkMicrophone()).ok).toBe(true);
    navigator.mediaDevices.getUserMedia.mockRejectedValueOnce(Object.assign(new Error('x'), { name: 'NotAllowedError' }));
    expect(await checkMicrophone()).toMatchObject({ ok: false, code: 'denied' });
    navigator.mediaDevices.getUserMedia.mockRejectedValueOnce(Object.assign(new Error('x'), { name: 'NotFoundError' }));
    expect(await checkMicrophone()).toMatchObject({ ok: false, code: 'missing' });
  });
});

describe('useRecorder without browser support', () => {
  it('is flagged unsupported', () => {
    vi.stubGlobal('MediaRecorder', undefined);
    const { result } = renderHook(() => useRecorder());
    expect(result.current.supported).toBe(false);
    expect(result.current.status).toBe('unsupported');
    vi.unstubAllGlobals();
  });
});
