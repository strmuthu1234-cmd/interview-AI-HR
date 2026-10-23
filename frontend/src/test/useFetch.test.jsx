import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api/client', () => ({ api: { get: vi.fn() }, errorMessage: (e) => e.message }));
import { api } from '../api/client';
import { useFetch } from '../hooks/useFetch';

describe('useFetch', () => {
  beforeEach(() => api.get.mockReset());

  it('only reports loading for the first load; reload() keeps data so child state is not unmounted', async () => {
    api.get.mockResolvedValueOnce({ data: { n: 1 } }).mockResolvedValueOnce({ data: { n: 2 } });
    const { result } = renderHook(() => useFetch('/thing/'));
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.data).toEqual({ n: 1 }));
    expect(result.current.loading).toBe(false);

    let sawLoadingDuringReload = false;
    await act(async () => {
      const p = result.current.reload();
      sawLoadingDuringReload = result.current.loading;
      await p;
    });
    expect(sawLoadingDuringReload).toBe(false);
    expect(result.current.data).toEqual({ n: 2 });
  });

  it('exposes API errors as messages', async () => {
    api.get.mockRejectedValueOnce(new Error('boom'));
    const { result } = renderHook(() => useFetch('/x/'));
    await waitFor(() => expect(result.current.error).toBe('boom'));
    expect(result.current.loading).toBe(false);
  });

  it('shows loading again when the url changes', async () => {
    api.get.mockResolvedValue({ data: {} });
    const { result, rerender } = renderHook(({ u }) => useFetch(u), { initialProps: { u: '/a/' } });
    await waitFor(() => expect(result.current.loading).toBe(false));
    api.get.mockImplementationOnce(() => new Promise(() => {}));
    rerender({ u: '/b/' });
    await waitFor(() => expect(result.current.loading).toBe(true));
  });
});
