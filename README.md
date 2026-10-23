# AI HR Recruitment & Interview System

Resume screening → HR-approved shortlist → structured 20-question AI interview (voice or text, **one question at a time**) → evidence-based evaluation → PDF report → **HR makes every final decision**.

* **Backend:** Django 5.2 · Django REST Framework · JWT · Celery/Redis · PostgreSQL (SQLite fallback for dev/tests) · PyMuPDF · python-docx · ReportLab
* **Frontend:** React 18 + Vite · Tailwind CSS · React Router · Axios · Recharts
* **AI:** OpenAI or Anthropic Claude (structured JSON), or an explicit, clearly-labelled **mock testing mode**
* API docs: `/api/docs/` (Swagger) · [docs/API.md](docs/API.md) (endpoint/permission matrix, sequencing and scoring rules)

> AI scores and bands are decision-support only. Nothing in the system accepts, rejects or hires a candidate automatically.

---

## 1. What is verified, and what is not

Honest status after building and testing this project on Windows 11 (Python 3.13, Node 24):

| Area | Status |
|---|---|
| Backend unit + API tests (`pytest`) | **38 passing** – parsing, scoring, upload validation, permissions, tenant isolation, interview sequencing, idempotent retries, evaluation maths, reports/PDF/CSV, retention |
| Frontend tests (`vitest`) | **28 passing** – one-question-at-a-time room, network-error recovery, recorder hook, consent gate, upload validation |
| Manual end-to-end in a real browser | **Done** (login → settings → ranked candidates → shortlist approval → question review → invitation → candidate interview incl. reload/resume → submission → HR report). One bug found this way (invitation link vanished after reload) was fixed and has a regression test |
| PDF report | Generated and visually inspected |
| **Real AI providers (OpenAI / Anthropic)** | **Not exercised – no API keys were available.** Request/response handling is covered by tests using fake clients that return provider-shaped JSON. First run with a real key may need prompt/model tuning |
| **Microphone recording / speech-to-text / text-to-speech** | **Not exercised with real hardware.** The recorder hook is tested with a mocked `MediaRecorder`; the voice upload endpoint is tested server-side. Please test in Chrome/Edge with a microphone (Tamil recognition depends on browser support) |
| **PostgreSQL, Redis/Celery workers, S3, Docker** | **Not exercised on this machine** (none installed). Code is environment-driven and migrations are plain Django; tests ran on SQLite with Celery in eager mode. `docker-compose.yml` is untested |
| Scanned-PDF OCR | Optional (`OCR_ENABLED=true`, needs Tesseract); not tested. Without it, image-only PDFs fail with a clear message |

## 2. Quick start (local development)

```bash
# --- backend ---
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example ../.env        # then edit; for a quick local run set DJANGO_DEBUG=true and CELERY_TASK_ALWAYS_EAGER=true
python manage.py migrate
python manage.py seed_demo --with-resumes   # demo org, users (passwords from DEMO_*_PASSWORD or printed once), sample job + 11 synthetic resumes
python manage.py runserver 8000

# --- frontend (second terminal) ---
cd frontend
npm install
npm run dev                        # http://localhost:5173  (proxies /api to :8000)
```

Sign in at <http://localhost:5173/login> with the `hr` / `admin` demo users.
For the interview steps without an AI key, an **admin** can choose *Settings → AI provider → Mock testing mode*. Every mock output is labelled MOCK in the UI, in reports and in the PDF.

### PostgreSQL + Redis locally

```bash
createdb hrai
# .env
DATABASE_URL=postgres://user:password@localhost:5432/hrai
REDIS_URL=redis://localhost:6379/0
CELERY_TASK_ALWAYS_EAGER=false
# separate terminals
celery -A config worker -l info          # on Windows add:  --pool=solo
celery -A config beat -l info            # daily retention purge
```

### Tests

```bash
cd backend  && python -m pytest          # SQLite, eager Celery, no network, no AI keys
cd frontend && npm test
```

Synthetic test data: `python manage.py export_samples` writes `samples/job_python_full_stack.json` and 11 fictional resumes (PDF/DOCX) incl. edge cases: prompt-injection text, protected-attribute lines, duplicate email, weak/irrelevant profiles. Resumes are already exported in [samples/](samples).

## 3. Configuration

Everything is configured through environment variables – see [.env.example](.env.example) (fully commented). Secrets are never in the repo or the UI.

| What | Variable(s) | Notes |
|---|---|---|
| AI provider | `AI_PROVIDER` (`openai`/`anthropic`/`mock`), `AI_MODEL`, `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | Admins can also pick provider/model under **Settings** (keys stay server-side). With no provider, resume screening still works; question generation and answer evaluation return a clear *"AI not configured"* error – no fake output. |
| Resume data to AI | Settings → *Allow AI processing of resume content* (off by default) | When off, nothing resume-derived is sent to a provider. When on, text is de-identified first (name, email, phone, links, protected attributes and instruction-like lines removed). |
| Speech-to-text | Browser (default) or `OPENAI_API_KEY` + Settings → *Server STT* | Candidates always review/edit the transcript before submitting. |
| Storage | `MEDIA_ROOT` or `USE_S3=true` + `AWS_*` | Files are private; served only via short-lived signed URLs to authorised HR users. |
| Email | `EMAIL_*` | Without SMTP, links are shown once in the UI (copy & send yourself). |
| Retention | Settings → Data retention | Daily Celery beat task deletes old audio/resumes/interviews. |

First production admin: `ADMIN_PASSWORD=… python manage.py create_admin --org "Acme" --username jane --email jane@acme.com`

## 4. How it works

1. **Job** – required/preferred skills, experience range, mandatory qualifications, shortlist slots, language.
2. **Bulk upload (1–50 PDF/DOCX)** – validated (extension, size, magic bytes, embedded JavaScript/macros), de-duplicated by SHA-256 (and by email), text extracted, parsed into a structured profile, scored in background tasks.
3. **Scoring** – deterministic and explainable (35 required skills · 25 experience · 20 projects · 10 preferred · 10 qualifications; weights editable). Each credit stores the supporting resume line. Missing information is never invented; protected-attribute lines are removed before scoring; instruction-like text in resumes is ignored and flagged to HR. Optional AI adds a narrative and project-relevance ratings (blended 50/50 with keyword score) but never sets the score alone.
4. **Shortlist** – top N shown (fewer if fewer resumes). HR can add/remove, then approves → 20 questions per candidate are generated (5 fixed general + 15 resume-grounded technical; technologies not in the resume/job are rejected; if 15 valid questions cannot be produced generation **fails visibly** rather than padding).
5. **HR reviews/edits questions → approves → creates invitation** (secret link, expiry, optional email, revoke/regenerate).
6. **Candidate interview** – instructions + explicit recording-consent choice, microphone check, AI interviewer reads each question (browser TTS), voice recording with pause/resume/replay/re-record **or** typing, transcript review, explicit Submit. The server enforces the sequence; reload/crash/offline retries are safe.
7. **Evaluation** – per answer: rubric sub-scores from the model, final 0–10 computed server-side, with strong points, missing points, possible inaccuracies, suggestions, confidence and verified evidence quotes. Accent/voice/grammar are explicitly excluded.
8. **Report** – 20% resume + 15% general + 65% technical, advisory band, strengths/gaps by skill, summary with stated uncertainty, full Q&A breakdown, PDF + CSV, comparison view.
9. **HR decision** – Selected / Rejected / On hold with comments, author and timestamp. Overrides and disputes are audited.

## 5. Security & fairness measures implemented

JWT auth with refresh rotation · role-based permissions on every endpoint (HR/admin/candidate-token) and org-scoped queries · invitation tokens stored hashed · rate limiting (login, uploads, candidates) · strict file validation · private files via signed URLs · recording only with consent · audit log (logins, decisions, exports, recording access) · CSV formula-injection guard · prompt-injection defences (data delimiting, line stripping, deterministic scoring) · PII/protected-attribute stripping before AI calls · candidates never receive reference answers or scores unless HR enables feedback · production settings enforce HTTPS/HSTS/secure cookies.

Known limitations: tokens are kept in `sessionStorage` (XSS-exposed; add a CSP at your proxy); no at-rest encryption beyond what your DB/S3 provides; keyword-based qualification matching must be verified by HR; browser speech recognition may send audio to the browser vendor (disclosed to candidates); the session time limit is informational (it does not auto-expire an interview).

## 6. Deployment

### Docker Compose (PostgreSQL, Redis, gunicorn, Celery worker + beat, nginx)

```bash
cp .env.example .env          # fill DJANGO_SECRET_KEY, POSTGRES_PASSWORD, FRONTEND_URL, AI keys …
docker compose up -d --build
docker compose exec backend python manage.py create_admin --org "Acme" --username admin --email admin@acme.com
```

nginx serves the React build and proxies `/api` to Django on the same origin (required for the resume PDF preview and to avoid CORS). Put TLS in front (load balancer/Caddy/Traefik) and forward `X-Forwarded-Proto`. For plain-HTTP local Docker testing set `SECURE_SSL_REDIRECT=false`. Back up the `pgdata` and `media` volumes (or use S3).

### Checklist

* [ ] `DJANGO_DEBUG=false`, strong `DJANGO_SECRET_KEY`, correct `DJANGO_ALLOWED_HOSTS` / `FRONTEND_URL`
* [ ] HTTPS everywhere; add CSP/other headers at the proxy
* [ ] PostgreSQL + Redis; at least one Celery worker and one beat
* [ ] AI provider key set; decide on *Allow AI processing of resume content*; review privacy notice/legal basis for recording and automated assessment in your jurisdiction (e.g. GDPR, local employment law)
* [ ] SMTP configured (or share links manually); S3 or persistent volume for media
* [ ] Retention values set; backups scheduled; admin accounts created with `create_admin`

## 7. Project layout

```
backend/   config/ (settings, celery, urls) · apps/core (defaults, auth, audit, tasks) · apps/accounts · apps/recruitment (jobs, resumes, screening, shortlist)
           apps/interviews (flow state machine, questions, evaluation, scoring, PDF) · apps/ai (provider clients, STT) · tests/
frontend/  src/pages/hr (dashboard, jobs, screening, candidates, interviews, reports, settings) · src/pages/candidate (entry, room) · src/hooks (recorder, speech) · src/test
docs/API.md · samples/ · docker-compose.yml · .env.example
```

## 8. Development phases – status

| Phase | Status |
|---|---|
| 1 Foundation (Django, React, DB models + migrations, auth, dashboard shell) | ✅ done, tested |
| 2 Resume screening (upload, extraction, scoring, shortlist UI) | ✅ done, tested (rule-based; AI-assisted path contract-tested only) |
| 3 Interview engine (20 questions, sequential flow, text evaluation) | ✅ done, tested; real LLM not run |
| 4 Voice (recording, STT, TTS, consent, storage) | ⚠️ implemented; needs hands-on test with a microphone & real STT |
| 5 Evaluation & reporting (weights, comparison, PDF/CSV, HR decisions) | ✅ done, tested |
| 6 Testing & deployment (tests, Docker, guide) | ✅ tests; ⚠️ Docker files untested here |
