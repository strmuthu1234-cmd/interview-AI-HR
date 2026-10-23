import axios from 'axios';

const baseURL = import.meta.env.VITE_API_URL || '/api';

// Tokens live in sessionStorage (cleared when the tab closes). Every access is wrapped:
// storage may be unavailable (private mode / blocked cookies).
export const tokens = {
  get access() { try { return sessionStorage.getItem('hr_access'); } catch { return null; } },
  get refresh() { try { return sessionStorage.getItem('hr_refresh'); } catch { return null; } },
  set({ access, refresh }) {
    try {
      if (access) sessionStorage.setItem('hr_access', access);
      if (refresh) sessionStorage.setItem('hr_refresh', refresh);
    } catch { /* ignore */ }
  },
  clear() { try { sessionStorage.removeItem('hr_access'); sessionStorage.removeItem('hr_refresh'); } catch { /* ignore */ } },
};

export const api = axios.create({ baseURL, timeout: 60000 });

api.interceptors.request.use((config) => {
  const t = tokens.access;
  if (t) config.headers.Authorization = `Bearer ${t}`;
  return config;
});

let refreshing = null;
api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const { config, response } = error;
    if (response?.status === 401 && tokens.refresh && config && !config._retried && !config.url?.includes('/auth/')) {
      config._retried = true;
      try {
        refreshing = refreshing || axios.post(`${baseURL}/auth/refresh/`, { refresh: tokens.refresh }).finally(() => { refreshing = null; });
        const { data } = await refreshing;
        tokens.set(data);
        config.headers.Authorization = `Bearer ${data.access}`;
        return api(config);
      } catch {
        tokens.clear();
        window.dispatchEvent(new Event('hr-auth-expired'));
      }
    }
    return Promise.reject(error);
  },
);

/** Axios instance for the candidate interview: authenticates ONLY with the invitation token. */
export function candidateApi(token) {
  return axios.create({ baseURL, timeout: 60000, headers: { Authorization: `Invitation ${token}` } });
}

/** Human-readable message from any API/network error. */
export function errorMessage(err, fallback = 'Something went wrong. Please try again.') {
  if (err?.response) {
    const d = err.response.data;
    if (typeof d === 'string') return d.slice(0, 200);
    if (d?.detail) return d.detail;
    if (d && typeof d === 'object') {
      const first = Object.entries(d)[0];
      if (first) return `${first[0]}: ${Array.isArray(first[1]) ? first[1][0] : first[1]}`;
    }
    return `${fallback} (${err.response.status})`;
  }
  if (err?.code === 'ECONNABORTED' || err?.message === 'Network Error') return 'Network problem – please check your connection and try again.';
  return err?.message || fallback;
}

export const isNetworkError = (err) => !err?.response;
export const errorCode = (err) => err?.response?.data?.code;
