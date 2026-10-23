import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { errorMessage, tokens } from '../api/client';
import { AuthProvider, RequireAuth } from '../auth/AuthContext';
import { TagInput } from '../components/ui';
import { fmtClock, fmtDuration, fmtScore, bandTone } from '../lib/format';
import { validateSelection } from '../pages/hr/JobDetail';
import { Welcome } from '../pages/candidate/InterviewEntry';

const file = (name, size = 1000) => ({ name, size });

describe('bulk upload validation', () => {
  it('accepts PDF/DOCX and reports problems for everything else', () => {
    const { accepted, problems } = validateSelection([], [file('a.pdf'), file('b.docx'), file('c.txt'), file('d.pdf', 6 * 1024 * 1024), file('e.pdf', 0)]);
    expect(accepted.map((f) => f.name)).toEqual(['a.pdf', 'b.docx']);
    expect(problems).toHaveLength(3);
    expect(problems.join(' ')).toMatch(/only PDF and DOCX/);
    expect(problems.join(' ')).toMatch(/larger than 5 MB/);
  });
  it('detects duplicates in the selection and enforces the 50 file limit', () => {
    const existing = Array.from({ length: 49 }, (_, i) => file(`r${i}.pdf`, 10 + i));
    const { accepted, problems } = validateSelection(existing, [file('r0.pdf', 10), file('new1.pdf'), file('new2.pdf')]);
    expect(accepted.map((f) => f.name)).toEqual(['new1.pdf']);
    expect(problems.some((p) => /already selected/.test(p))).toBe(true);
    expect(problems.some((p) => /limit of 50/.test(p))).toBe(true);
  });
});

describe('formatting helpers', () => {
  it('formats scores, durations and bands', () => {
    expect(fmtScore(84.85, 2)).toBe('84.85');
    expect(fmtScore(80.0)).toBe('80');
    expect(fmtScore(null)).toBe('—');
    expect(fmtClock(75)).toBe('01:15');
    expect(fmtDuration(125)).toBe('2m 5s');
    expect(bandTone('Strong match')).toBe('green');
    expect(bandTone('Significant gaps identified')).toBe('red');
  });
  it('turns API errors into readable messages', () => {
    expect(errorMessage({ response: { status: 400, data: { detail: 'Bad thing' } } })).toBe('Bad thing');
    expect(errorMessage({ response: { status: 400, data: { title: ['Required'] } } })).toBe('title: Required');
    expect(errorMessage({ message: 'Network Error' })).toMatch(/network problem/i);
  });
});

describe('TagInput', () => {
  it('adds on Enter, ignores duplicates, removes on click', async () => {
    const onChange = vi.fn();
    const { rerender } = render(<TagInput value={['Python']} onChange={onChange} />);
    await userEvent.type(screen.getByRole('textbox'), 'Django{Enter}');
    expect(onChange).toHaveBeenLastCalledWith(['Python', 'Django']);
    rerender(<TagInput value={['Python']} onChange={onChange} />);
    await userEvent.type(screen.getByRole('textbox'), 'python{Enter}');
    expect(onChange).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole('button', { name: /remove python/i }));
    expect(onChange).toHaveBeenLastCalledWith([]);
  });
});

describe('route protection', () => {
  it('redirects anonymous users to the login page', async () => {
    tokens.clear();
    render(
      <MemoryRouter initialEntries={['/secret']}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<p>login page</p>} />
            <Route path="/secret" element={<RequireAuth><p>secret</p></RequireAuth>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText('login page')).toBeInTheDocument());
    expect(screen.queryByText('secret')).not.toBeInTheDocument();
  });
});

describe('candidate welcome screen', () => {
  const info = { candidate_first_name: 'Asha', job_title: 'Dev', company: 'Acme', duration_minutes: 45, instructions: ['One question at a time.'] };
  it('requires instruction acceptance and an explicit recording choice before starting', async () => {
    const onStart = vi.fn().mockResolvedValue();
    render(<Welcome info={info} onStart={onStart} />);
    const start = screen.getByRole('button', { name: /start interview/i });
    expect(start).toBeDisabled();
    await userEvent.click(screen.getByLabelText(/read and accept/i));
    expect(start).toBeDisabled(); // still no consent choice
    await userEvent.click(screen.getByLabelText(/do not want audio stored/i));
    expect(start).toBeEnabled();
    await userEvent.click(start);
    expect(onStart).toHaveBeenCalledWith(false);
  });
  it('passes consent=true when the candidate agrees to recording', async () => {
    const onStart = vi.fn().mockResolvedValue();
    render(<Welcome info={info} onStart={onStart} />);
    await userEvent.click(screen.getByLabelText(/read and accept/i));
    await userEvent.click(screen.getByLabelText(/i agree to my voice answers/i));
    await userEvent.click(screen.getByRole('button', { name: /start interview/i }));
    expect(onStart).toHaveBeenCalledWith(true);
  });
  it('shows a clear message when the microphone is unavailable', async () => {
    Object.defineProperty(navigator, 'mediaDevices', { value: undefined, configurable: true });
    render(<Welcome info={info} onStart={vi.fn()} />);
    await userEvent.click(screen.getByRole('button', { name: /test microphone/i }));
    expect(await screen.findByRole('status')).toHaveTextContent(/cannot record audio/i);
  });
});
