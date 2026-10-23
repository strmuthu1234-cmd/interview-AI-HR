import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import InterviewRoom from '../pages/candidate/InterviewRoom';

const info = { language: 'en', progress: { answered: 0 }, settings: { max_answer_seconds: 300, stt_provider: 'browser' } };

const mkQuestion = (n, extra = {}) => ({ id: `q${n}`, number: n, total: 20, text: `Question text number ${n}?`, section: n <= 5 ? 'general' : 'technical', is_self_introduction: n === 1, pending_audio: null, settings: {}, ...extra });
const progress = (answered) => ({ answered, total: 20, current_number: answered + 1 });

function makeApi({ questions = [mkQuestion(1), mkQuestion(2)], failFirstPost = null } = {}) {
  let i = 0;
  const posts = [];
  let failed = false;
  const api = {
    get: vi.fn(async () => {
      if (i >= questions.length) return { data: { done: true, progress: progress(20) } };
      return { data: { done: false, question: questions[i], progress: progress(i) } };
    }),
    post: vi.fn(async (url, body) => {
      posts.push({ url, body });
      if (url.endsWith('/answer/')) {
        if (failFirstPost && !failed) { failed = true; throw failFirstPost; }
        i += 1;
        return { data: { saved: true, progress: progress(i) } };
      }
      return { data: {} };
    }),
  };
  return { api, posts };
}

const renderRoom = (api, props = {}) => render(<InterviewRoom api={api} sessionId="s1" info={info} consent={false} onFinished={vi.fn()} {...props} />);

beforeEach(() => { vi.stubGlobal('speechSynthesis', undefined); });

describe('InterviewRoom – one question at a time', () => {
  it('shows only the current question and progress', async () => {
    const { api } = makeApi();
    renderRoom(api);
    expect(await screen.findByTestId('question-text')).toHaveTextContent('Question text number 1?');
    expect(screen.getByTestId('question-counter')).toHaveTextContent('Question 1 of 20');
    expect(screen.queryByText(/number 2\?/)).not.toBeInTheDocument();
    expect(screen.getAllByText(/Question text number/)).toHaveLength(1);
    expect(api.get).toHaveBeenCalledTimes(1);
  });

  it('does not allow submitting an empty answer and never advances on its own', async () => {
    const { api, posts } = makeApi();
    renderRoom(api);
    await screen.findByTestId('question-text');
    expect(screen.getByRole('button', { name: /submit answer/i })).toBeDisabled();
    await new Promise((r) => setTimeout(r, 150)); // silence / pause: nothing happens
    expect(posts).toHaveLength(0);
    expect(screen.getByTestId('question-counter')).toHaveTextContent('Question 1 of 20');
  });

  it('submits the typed answer for the active question and then loads the next one', async () => {
    const { api, posts } = makeApi();
    renderRoom(api);
    await screen.findByTestId('question-text');
    await userEvent.type(screen.getByLabelText(/your answer/i), 'My detailed answer');
    await userEvent.click(screen.getByRole('button', { name: /submit answer/i }));
    await waitFor(() => expect(screen.getByTestId('question-text')).toHaveTextContent('number 2?'));
    expect(posts[0].url).toBe('/interviews/s1/answer/');
    expect(posts[0].body).toMatchObject({ question_id: 'q1', text: 'My detailed answer', input_mode: 'text', skip: false });
    expect(posts[0].body.client_submission_id).toBeTruthy();
    expect(screen.getByLabelText(/your answer/i)).toHaveValue(''); // fresh answer box for the next question
  });

  it('keeps the answer and retries with the SAME submission id after a network error', async () => {
    const { api, posts } = makeApi({ failFirstPost: Object.assign(new Error('Network Error'), { code: 'ERR_NETWORK' }) });
    renderRoom(api);
    await screen.findByTestId('question-text');
    await userEvent.type(screen.getByLabelText(/your answer/i), 'Important answer');
    await userEvent.click(screen.getByRole('button', { name: /submit answer/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not reach the server/i);
    expect(screen.getByLabelText(/your answer/i)).toHaveValue('Important answer');
    expect(screen.getByTestId('question-counter')).toHaveTextContent('Question 1 of 20');
    await userEvent.click(screen.getByRole('button', { name: /submit answer/i }));
    await waitFor(() => expect(screen.getByTestId('question-text')).toHaveTextContent('number 2?'));
    expect(posts[0].body.client_submission_id).toBe(posts[1].body.client_submission_id);
  });

  it('reloads the server-side question when the server says it is not the active one', async () => {
    const err = Object.assign(new Error('x'), { response: { status: 409, data: { code: 'wrong_question', detail: 'not active' } } });
    const { api } = makeApi({ failFirstPost: err });
    renderRoom(api);
    await screen.findByTestId('question-text');
    await userEvent.type(screen.getByLabelText(/your answer/i), 'answer');
    await userEvent.click(screen.getByRole('button', { name: /submit answer/i }));
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
  });

  it('lets the candidate skip, which is sent explicitly as skip=true', async () => {
    const { api, posts } = makeApi();
    renderRoom(api);
    await screen.findByTestId('question-text');
    await userEvent.click(screen.getByRole('button', { name: /can’t answer/i }));
    await waitFor(() => expect(posts[0]?.body.skip).toBe(true));
    expect(posts[0].body.text).toBe('');
  });

  it('restores an unsent draft after a reload', async () => {
    localStorage.setItem('interview-draft:s1:q1', 'half written answer');
    const { api } = makeApi();
    renderRoom(api);
    await screen.findByTestId('question-text');
    expect(screen.getByLabelText(/your answer/i)).toHaveValue('half written answer');
  });

  it('shows the finish screen after the last question and submits the interview', async () => {
    const onFinished = vi.fn();
    const { api, posts } = makeApi({ questions: [] });
    renderRoom(api, { onFinished });
    expect(await screen.findByText(/answered all 20 questions/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /submit interview/i }));
    await waitFor(() => expect(onFinished).toHaveBeenCalled());
    expect(posts.at(-1).url).toBe('/interviews/s1/complete/');
  });

  it('offers voice mode only with recording consent or dictation support and explains microphone problems', async () => {
    const { api } = makeApi();
    renderRoom(api, { consent: true });
    await screen.findByTestId('question-text');
    const tablist = screen.getByRole('tablist', { name: /answer method/i });
    expect(within(tablist).getAllByRole('tab')).toHaveLength(2);
    expect(screen.getByText(/not supported in this browser/i)).toBeInTheDocument(); // jsdom has no MediaRecorder
    expect(screen.getByRole('button', { name: /start recording/i })).toBeDisabled();
  });

  it('never exposes evaluation or reference data in the DOM', async () => {
    const { api } = makeApi({ questions: [mkQuestion(1, { expected_points: ['SECRET'] })] });
    renderRoom(api);
    await screen.findByTestId('question-text');
    expect(document.body.textContent).not.toMatch(/SECRET|score|evaluation/i);
  });
});
