# API reference

Interactive OpenAPI docs (Swagger UI): **`/api/docs/`** · schema: `/api/schema/`.
All paths are under `/api/`. JSON unless noted. Errors: `{"detail": "...", "code": "..."}`.

## Authentication

| Who | How |
|---|---|
| HR / Admin | `POST /auth/login/` → `{access, refresh, user}`; send `Authorization: Bearer <access>`; `POST /auth/refresh/` rotates tokens. Login is rate-limited (`THROTTLE_LOGIN`). |
| Candidate | No account. The secret link `…/interview/<token>` token is sent as `Authorization: Invitation <token>`. Only its SHA-256 hash is stored. A token opens **one** interview only. |

AI-not-configured errors return **503** `{"code": "ai_not_configured"}`; provider failures **502** `ai_provider_error`.

## Permissions matrix

`HR` = HR manager or admin · `Admin` = admin only · `Cand` = candidate invitation token (own session only)

| Endpoint | Method | Who | Notes |
|---|---|---|---|
| `/auth/login/`, `/auth/refresh/` | POST | public | |
| `/auth/me/` | GET | HR | |
| `/users/`, `/users/{id}/` | GET POST PATCH | Admin | org-scoped; cannot disable/demote self |
| `/audit-logs/` | GET | Admin | append-only |
| `/settings/` | GET / PATCH | HR read / Admin write | weights, AI, voice, retention. Validated (weights total 100) |
| `/jobs/`, `/jobs/{id}/` | GET POST PUT PATCH | HR | no DELETE |
| `/resumes/bulk-upload/` | POST multipart `job`, `files[]` (1–50) | HR | validates type, size, magic bytes, active content; duplicate detection by SHA-256 |
| `/resumes/analyze/` | POST `{job_id, batch_id?}` | HR | re-score with current rubric/profile corrections (202) |
| `/batches/`, `/batches/{id}/` | GET | HR | screening progress |
| `/candidates/` | GET `?job&status&min_score&skill&search` | HR | |
| `/candidates/{id}/` | GET / PATCH | HR | PATCH = HR correction of extracted data (original parse kept) |
| `/candidates/{id}/dispute/` | POST `{note, adjusted_score?}` | HR | human override of an assessment |
| `/candidates/{id}/resume-url/` | GET | HR | 5-minute signed URL → `/files/resume/<token>/` |
| `/shortlists/`, `/shortlists/approve/` | GET / POST `{shortlist_id, candidate_ids}` | HR | approval creates sessions and queues 20-question generation |
| `/interviews/` , `/interviews/{id}/` | GET (PATCH `reveal_results`) | HR | detail includes questions, answers, evaluations |
| `/interviews/{id}/generate-questions/` | POST | HR | retry after fixing AI config |
| `/interviews/{id}/questions/{qid}/` | PATCH | HR | only before the interview starts; re-opens approval |
| `/interviews/{id}/approve-questions/` | POST | HR | requires exactly 20 questions |
| `/interviews/create/` | POST `{session_id, expires_in_days?, send_email?}` | HR | returns the one-time link |
| `/interviews/{id}/regenerate-link/`, `/revoke/` | POST | HR | |
| `/interviews/{id}/overrides/` | POST `{answer_id, score, reason}` | HR | disputed evaluations; recalculates report |
| `/interviews/{id}/report/` | GET | HR | JSON report (+ `/report/regenerate/` POST, `/report/pdf/` GET) |
| `/interviews/{id}/answers/{aid}/audio-url/` | GET | HR | signed URL → `/files/audio/<token>/` (audited) |
| `/hr/decisions/` | GET, POST `{session_id, decision, comments}` | HR | `selected` / `rejected` / `on_hold`; **only** way to set an outcome |
| `/reports/compare/?sessions=a,b` | GET | HR | 2–6 completed interviews |
| `/reports/export/?job=` | GET | HR | CSV (formula-injection safe) |
| `/dashboard/stats/` | GET | HR | |
| `/interviews/access/` | POST | Cand | what the candidate may see (no scores, no reference answers) |
| `/interviews/{id}/accept-instructions/` | POST `{accept: true, recording_consent: bool}` | Cand | both are mandatory |
| `/interviews/{id}/question/` | GET | Cand | **only the active question**; 409 `not_started` before instructions are accepted |
| `/interviews/{id}/voice-upload/` | POST multipart `audio, duration, transcript?` | Cand | needs consent; stored for the active question, not yet submitted |
| `/interviews/{id}/answer/` | POST `{question_id, text, input_mode, client_submission_id, skip?}` | Cand | see rules below |
| `/interviews/{id}/progress/` | GET | Cand | |
| `/interviews/{id}/complete/` | POST | Cand | 409 until all 20 answered; queues report generation |
| `/interviews/{id}/results/` | GET | Cand | 403 unless HR enabled feedback sharing |

## Interview sequencing rules (enforced server-side)

* The session stores `current_index`. `GET question` returns only that question.
* `POST answer` must carry the active `question_id`, otherwise **409 `wrong_question`**; answering twice → **409 `already_answered`**; skipping ahead is impossible.
* `client_submission_id` makes retries idempotent (network failures): a repeat returns `200 {duplicate: true}` and never advances twice.
* The next question unlocks only after the answer is stored **and** an evaluation attempt is recorded. A provider outage records `evaluation.status = failed` (retried later) and does not block the candidate.
* Silence, pauses or inactivity never advance the interview.
* Skipped answers are stored as `unavailable` and excluded from scores (listed in report coverage).

## Scoring formulas

* **Resume match** = Σ category score × weight (default 35 required skills, 25 experience, 20 projects, 10 preferred, 10 qualifications). Not-applicable categories are dropped and weights renormalised.
* **Answer score (0–10)** = Σ criterion score × weight, computed by the server from the model's per-criterion scores (technical 40/25/20/15; behavioral 30/25/30/15).
* **Final** = 0.20 × resume + 0.15 × general + 0.65 × technical (all normalised to 100). Bands: 85+ Strong, 70–84 Good, 50–69 Needs further review, <50 Significant gaps. Advisory only.
