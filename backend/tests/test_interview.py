"""End-to-end interview flow (mock testing mode), backend sequencing rules and report scoring."""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.models import Organization
from apps.interviews.models import AnswerEvaluation, CandidateAnswer, InterviewSession
from apps.interviews.services import questions as qsvc
from apps.recruitment.models import Candidate, Shortlist

ANSWER = ("I used Django REST Framework with PostgreSQL because it keeps the API consistent. For example, in my project I implemented "
          "JWT authentication and role-based access control, and I tested the endpoints with pytest and Git based reviews.")


def candidate_client(token):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Invitation {token}")
    return c


@pytest.fixture
def approved(hr_client, screened_job, django_capture_on_commit_callbacks):
    sl = Shortlist.objects.get(job=screened_job, status="proposed")
    ids = [str(e.candidate_id) for e in sl.entries.order_by("rank")[:3]]
    with django_capture_on_commit_callbacks(execute=True):
        r = hr_client.post("/api/shortlists/approve/", {"shortlist_id": str(sl.pk), "candidate_ids": ids}, format="json")
    assert r.status_code == 200, r.content
    return r.data["interview_sessions"]


def invite(hr_client, session_id):
    assert hr_client.post(f"/api/interviews/{session_id}/approve-questions/").status_code == 200
    r = hr_client.post("/api/interviews/create/", {"session_id": session_id, "send_email": True}, format="json")
    assert r.status_code == 201, r.content
    return r.data["link"].rsplit("/", 1)[1]


def start(cc, sid, consent=False):
    r = cc.post(f"/api/interviews/{sid}/accept-instructions/", {"accept": True, "recording_consent": consent}, format="json")
    assert r.status_code == 200, r.content


def answer_all(cc, sid, n=20, text=ANSWER):
    for i in range(n):
        q = cc.get(f"/api/interviews/{sid}/question/").data["question"]
        assert q["number"] == i + 1
        r = cc.post(f"/api/interviews/{sid}/answer/", {"question_id": q["id"], "text": text, "input_mode": "text", "client_submission_id": f"s{i}"}, format="json")
        assert r.status_code == 201, r.content


# ------------------------------------------------------------ generation
def test_approval_generates_exactly_20_questions(approved):
    assert len(approved) == 3
    for sid in approved:
        s = InterviewSession.objects.get(pk=sid)
        assert s.status == "draft" and s.is_mock
        qs = list(s.questions.order_by("index"))
        assert len(qs) == 20
        assert [q.section for q in qs] == ["general"] * 5 + ["technical"] * 15
        assert qs[0].is_self_introduction and "introduce yourself" in qs[0].text.lower()
        assert len({q.text for q in qs}) == 20
        assert all(q.expected_points for q in qs)
    assert Candidate.objects.filter(pk=InterviewSession.objects.get(pk=approved[0]).candidate_id, status="shortlisted").exists()


def test_shortlist_size_and_double_approval(hr_client, screened_job):
    sl = Shortlist.objects.get(job=screened_job, status="proposed")
    ids = [str(e.candidate_id) for e in sl.entries.all()]
    screened_job.shortlist_size = 2
    screened_job.save()
    r = hr_client.post("/api/shortlists/approve/", {"shortlist_id": str(sl.pk), "candidate_ids": ids}, format="json")
    assert r.status_code == 400 and "slots" in r.data["detail"]


def test_unconfigured_ai_gives_clear_error_not_fake_questions(hr_client, org, screened_job, django_capture_on_commit_callbacks, settings):
    org.settings = {}
    org.save()
    sl = Shortlist.objects.get(job=screened_job, status="proposed")
    cid = str(sl.entries.first().candidate_id)
    with django_capture_on_commit_callbacks(execute=True):
        sid = hr_client.post("/api/shortlists/approve/", {"shortlist_id": str(sl.pk), "candidate_ids": [cid]}, format="json").data["interview_sessions"][0]
    s = InterviewSession.objects.get(pk=sid)
    assert s.status == "generation_failed" and "No AI provider is configured" in s.generation_error
    assert s.questions.count() == 0
    assert hr_client.post(f"/api/interviews/{sid}/approve-questions/").status_code == 409
    assert hr_client.get("/api/settings/").data["ai_status"]["configured"] is False


class FakeClient:
    is_mock = False
    provider, model = "fake", "fake-1"

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def label(self):
        return "fake:fake-1"

    def complete_json(self, system, user, max_tokens=0):
        self.prompts.append((system, user))
        return self.replies.pop(0)


def _tq(text, tags=("Django",)):
    return {"text": text, "skill_tags": list(tags), "grounding": ["Resume lists Django"], "expected_points": ["a", "b", "c"], "difficulty": "intermediate"}


def test_ai_questions_reject_unsupported_technologies(job, org):
    org.settings = {"ai": {"provider": "openai", "allow_resume_sharing": True}}
    profile = {"skills": ["Python", "Django"], "technologies": ["Python", "Django"], "projects": [], "experience": [], "total_experience_years": 2}
    allowed = qsvc.allowed_technologies(job, profile)
    assert qsvc.unsupported_technologies("Explain how you would use Kubernetes with Django?", allowed) == ["kubernetes"]
    assert qsvc.unsupported_technologies("Explain Django ORM and PostgreSQL query tuning?", allowed) == []
    cleaned, why = qsvc._clean_question(_tq("How would you deploy Django on Kubernetes at scale?"), allowed)
    assert cleaned is None and "kubernetes" in why


def test_ai_generation_requires_resume_sharing_consent(job, org, monkeypatch):
    org.settings = {"ai": {"provider": "openai", "allow_resume_sharing": False}}
    org.save()
    monkeypatch.setattr("django.conf.settings.OPENAI_API_KEY", "test-key", raising=False)
    from apps.ai.errors import AIConfigurationError

    cand = Candidate.objects.create(organization=org, job=job, full_name="X", profile={"skills": ["Python"]})
    s = InterviewSession.objects.create(organization=org, candidate=cand, job=job)
    with pytest.raises(AIConfigurationError, match="Allow AI processing"):
        qsvc.generate_questions(s)


def test_ai_generation_exactly_15_or_fails(job, org, monkeypatch):
    org.settings = {"ai": {"provider": "openai", "allow_resume_sharing": True}}
    org.save()
    profile = {"skills": ["Python", "Django", "PostgreSQL"], "technologies": ["Python", "Django", "PostgreSQL"], "projects": [{"name": "Lib", "technologies": ["Django"], "description": ""}],
               "experience": [], "total_experience_years": 2}
    cand = Candidate.objects.create(organization=org, job=job, full_name="X", profile=profile)
    s = InterviewSession.objects.create(organization=org, candidate=cand, job=job)
    good = [_tq(f"Question number {i} about how Django handles request cycle detail {i}?") for i in range(15)]
    fake = FakeClient([{"questions": good[:10] + [_tq("Use Kubernetes with Django?")]}, {"questions": good[10:12]}])
    monkeypatch.setattr(qsvc, "get_client", lambda org: fake)
    with pytest.raises(qsvc.GenerationError, match="Only 12"):
        qsvc.generate_questions(s)
    assert s.questions.count() == 0  # nothing padded / stored
    fake2 = FakeClient([{"questions": good}])
    monkeypatch.setattr(qsvc, "get_client", lambda org: fake2)
    qsvc.generate_questions(s)
    assert s.questions.count() == 20
    assert "jane" not in fake2.prompts[0][1].lower()  # de-identified prompt


# ------------------------------------------------------------ interview flow
def test_full_interview_one_question_at_a_time(hr_client, approved, django_capture_on_commit_callbacks):
    sid = approved[0]
    token = invite(hr_client, sid)
    cc = candidate_client(token)

    info = cc.post("/api/interviews/access/").data
    assert info["available"] and info["progress"]["total"] == 20 and "expected_points" not in str(info)
    assert cc.get(f"/api/interviews/{sid}/question/").status_code == 409  # instructions not accepted yet
    assert cc.post(f"/api/interviews/{sid}/accept-instructions/", {"accept": False, "recording_consent": False}, format="json").status_code == 400
    start(cc, sid)

    q1 = cc.get(f"/api/interviews/{sid}/question/").data
    assert q1["question"]["number"] == 1 and q1["question"]["is_self_introduction"]
    assert "expected_points" not in q1["question"] and "evaluation" not in str(q1)
    # reloading never reveals or skips ahead
    assert cc.get(f"/api/interviews/{sid}/question/").data["question"]["id"] == q1["question"]["id"]

    # validation on the backend
    qid = q1["question"]["id"]
    assert cc.post(f"/api/interviews/{sid}/answer/", {"question_id": qid, "text": "   "}, format="json").status_code == 400
    other = InterviewSession.objects.get(pk=sid).questions.get(index=1)
    r = cc.post(f"/api/interviews/{sid}/answer/", {"question_id": str(other.id), "text": ANSWER}, format="json")
    assert r.status_code == 409 and r.data["code"] == "wrong_question"
    r = cc.post(f"/api/interviews/{sid}/answer/", {"question_id": qid, "text": "x" * 9000}, format="json")
    assert r.status_code == 400

    r = cc.post(f"/api/interviews/{sid}/answer/", {"question_id": qid, "text": ANSWER, "client_submission_id": "abc"}, format="json")
    assert r.status_code == 201 and r.data["progress"]["current_number"] == 2 and "feedback" not in r.data
    # network retry of the same submission is idempotent
    r = cc.post(f"/api/interviews/{sid}/answer/", {"question_id": qid, "text": ANSWER, "client_submission_id": "abc"}, format="json")
    assert r.status_code == 200 and r.data["duplicate"] and r.data["progress"]["current_number"] == 2
    assert CandidateAnswer.objects.filter(session_id=sid).count() == 1
    # re-answering a past question is impossible
    assert cc.post(f"/api/interviews/{sid}/answer/", {"question_id": qid, "text": ANSWER}, format="json").status_code == 409

    # resume on a brand-new client (browser closed) continues at question 2
    assert candidate_client(token).get(f"/api/interviews/{sid}/question/").data["question"]["number"] == 2
    # cannot complete early
    assert cc.post(f"/api/interviews/{sid}/complete/").status_code == 409

    for i in range(1, 20):
        q = cc.get(f"/api/interviews/{sid}/question/").data["question"]
        assert q["number"] == i + 1
        if i == 7:  # skipped question is marked unavailable, not invented
            cc.post(f"/api/interviews/{sid}/answer/", {"question_id": q["id"], "skip": True}, format="json")
        else:
            cc.post(f"/api/interviews/{sid}/answer/", {"question_id": q["id"], "text": ANSWER}, format="json")
    assert cc.get(f"/api/interviews/{sid}/question/").data["done"] is True
    assert AnswerEvaluation.objects.filter(answer__session_id=sid).count() == 20
    assert AnswerEvaluation.objects.filter(answer__session_id=sid, status="unavailable").count() == 1
    with django_capture_on_commit_callbacks(execute=True):
        assert cc.post(f"/api/interviews/{sid}/complete/").status_code == 200
    assert cc.post(f"/api/interviews/{sid}/complete/").status_code == 200  # idempotent
    s = InterviewSession.objects.get(pk=sid)
    assert s.status == "completed" and s.candidate.status == "interviewed"
    assert cc.post(f"/api/interviews/{sid}/answer/", {"question_id": qid, "text": ANSWER}, format="json").status_code in (409,)

    # ---- HR: report with the configured formula
    rep = hr_client.get(f"/api/interviews/{sid}/report/").data
    r = rep["report"]
    expected = round(0.20 * r["resume_score"] + 0.15 * r["general_score"] + 0.65 * r["technical_score"], 2)
    assert r["final_score"] == pytest.approx(expected, abs=0.011)
    assert r["band"] in {"Strong match", "Good match", "Needs further review", "Significant gaps identified"}
    assert r["coverage"]["unavailable"] == 1 and r["coverage"]["evaluated"] == 19
    assert any("MOCK" in u for u in r["uncertainty"]) and rep["is_mock"]
    assert len(rep["questions"]) == 20 and rep["questions"][7]["evaluation"]["status"] == "unavailable"
    names = [s["skill"].lower() for s in r["strengths"] + r["knowledge_gaps"]]
    assert len(names) == len(set(names)), "aliases such as React / React.js must be grouped into one skill"

    # AI never decides: no decision until HR records one
    assert rep["latest_decision"] is None
    assert Candidate.objects.get(pk=s.candidate_id).status == "interviewed"
    d = hr_client.post("/api/hr/decisions/", {"session_id": sid, "decision": "on_hold", "comments": "Need a second round"}, format="json")
    assert d.status_code == 201 and d.data["decided_by"] == "hr1"
    assert Candidate.objects.get(pk=s.candidate_id).status == "on_hold"
    assert hr_client.post("/api/hr/decisions/", {"session_id": sid, "decision": "maybe"}, format="json").status_code == 400
    assert hr_client.post("/api/hr/decisions/", {"session_id": sid, "decision": "selected", "comments": "ok"}, format="json").status_code == 201
    assert hr_client.get(f"/api/interviews/{sid}/report/").data["latest_decision"]["decision"] == "selected"

    # exports
    pdf = hr_client.get(f"/api/interviews/{sid}/report/pdf/")
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-" and pdf["Content-Type"] == "application/pdf"
    csv = hr_client.get("/api/reports/export/").content.decode()
    assert "Final score" in csv and "selected" in csv
    cmp_ = hr_client.get(f"/api/reports/compare/?sessions={sid}").data
    assert cmp_["candidates"][0]["final_score"] == r["final_score"]

    # HR override recalculates the report and is audited
    ans = CandidateAnswer.objects.get(session_id=sid, question__index=10)
    before = hr_client.get(f"/api/interviews/{sid}/report/").data["report"]["technical_score"]
    assert hr_client.post(f"/api/interviews/{sid}/overrides/", {"answer_id": str(ans.id), "score": 10, "reason": "Strong verbal answer"}, format="json").status_code == 200
    after = hr_client.get(f"/api/interviews/{sid}/report/").data["report"]["technical_score"]
    assert after >= before
    from apps.accounts.models import AuditLog

    assert AuditLog.objects.filter(action__in=["hr.decision", "evaluation.override", "interview.complete"]).count() >= 3


def test_candidate_can_only_access_own_session_and_not_hr_endpoints(hr_client, approved):
    a, b = approved[0], approved[1]
    ta, tb = invite(hr_client, a), invite(hr_client, b)
    ca = candidate_client(ta)
    assert ca.get(f"/api/interviews/{b}/question/").status_code == 403
    assert ca.get(f"/api/interviews/{a}/").status_code == 403  # HR detail
    assert ca.get("/api/candidates/").status_code == 403
    assert ca.get("/api/jobs/").status_code == 403
    assert ca.get(f"/api/interviews/{a}/report/").status_code == 403
    assert ca.post("/api/hr/decisions/", {"session_id": a, "decision": "selected"}, format="json").status_code == 403
    assert candidate_client("bogus-token").post("/api/interviews/access/").status_code == 401
    assert APIClient().post("/api/interviews/access/").status_code == 401
    # HR JWT cannot use candidate endpoints
    assert hr_client.get(f"/api/interviews/{a}/question/").status_code == 403


def test_revoked_and_expired_links(hr_client, approved):
    from datetime import timedelta

    from django.utils import timezone

    from apps.interviews.models import InterviewInvitation

    sid = approved[0]
    token = invite(hr_client, sid)
    cc = candidate_client(token)
    assert cc.post("/api/interviews/access/").status_code == 200
    InterviewInvitation.objects.filter(session_id=sid).update(expires_at=timezone.now() - timedelta(minutes=1))
    assert cc.post("/api/interviews/access/").status_code == 401
    new = hr_client.post(f"/api/interviews/{sid}/regenerate-link/").data["link"].rsplit("/", 1)[1]
    assert candidate_client(token).post("/api/interviews/access/").status_code == 401  # old token dead
    assert candidate_client(new).post("/api/interviews/access/").status_code == 200
    hr_client.post(f"/api/interviews/{sid}/revoke/")
    assert candidate_client(new).post("/api/interviews/access/").status_code == 401


def test_cannot_invite_before_questions_approved_and_editing_rules(hr_client, approved):
    sid = approved[0]
    assert hr_client.post("/api/interviews/create/", {"session_id": sid}, format="json").status_code == 409
    s = InterviewSession.objects.get(pk=sid)
    q = s.questions.get(index=6)
    r = hr_client.patch(f"/api/interviews/{sid}/questions/{q.pk}/", {"text": "Explain how Django ORM lazily evaluates querysets and why that matters?"}, format="json")
    assert r.status_code == 200 and not r.data["warnings"]
    r = hr_client.patch(f"/api/interviews/{sid}/questions/{q.pk}/", {"text": "Describe how you would run Kubernetes clusters for this team?"}, format="json")
    assert r.data["warnings"] and "kubernetes" in r.data["warnings"][0].lower()
    q.refresh_from_db()
    assert q.edited_by_id and q.original_text != q.text
    # editing re-opens approval; after approval + invitation + start, questions are frozen
    assert InterviewSession.objects.get(pk=sid).status == "draft"
    cc = candidate_client(invite(hr_client, sid))
    assert hr_client.patch(f"/api/interviews/{sid}/questions/{q.pk}/", {"text": "A brand new question about Python?"}, format="json").status_code == 200
    assert hr_client.post(f"/api/interviews/{sid}/approve-questions/").status_code == 200
    start(cc, sid)
    assert hr_client.patch(f"/api/interviews/{sid}/questions/{q.pk}/", {"text": "Another question about Python?"}, format="json").status_code == 409


def test_voice_upload_consent_validation_and_playback(hr_client, approved, anon):
    sid = approved[0]
    token = invite(hr_client, sid)
    cc = candidate_client(token)
    start(cc, sid, consent=False)
    webm = SimpleUploadedFile("a.webm", b"\x1a\x45\xdf\xa3" + b"0" * 2000, content_type="audio/webm")
    assert cc.post(f"/api/interviews/{sid}/voice-upload/", {"audio": webm, "duration": 5}, format="multipart").status_code == 403  # no consent
    # new interview with consent
    sid2 = approved[1]
    cc2 = candidate_client(invite(hr_client, sid2))
    start(cc2, sid2, consent=True)
    bad = SimpleUploadedFile("a.webm", b"this is not audio" * 20)
    assert cc2.post(f"/api/interviews/{sid2}/voice-upload/", {"audio": bad}, format="multipart").status_code == 400
    r = cc2.post(f"/api/interviews/{sid2}/voice-upload/", {"audio": SimpleUploadedFile("a.webm", b"\x1a\x45\xdf\xa3" + b"0" * 2000), "duration": 12, "transcript": ANSWER}, format="multipart")
    assert r.status_code == 201 and r.data["transcript"] == ANSWER and r.data["transcript_source"] == "browser"
    q = cc2.get(f"/api/interviews/{sid2}/question/").data["question"]
    assert q["pending_audio"]["transcript"] == ANSWER  # recoverable after reload
    r = cc2.post(f"/api/interviews/{sid2}/answer/", {"question_id": q["id"], "text": ANSWER, "input_mode": "voice"}, format="json")
    assert r.status_code == 201
    ans = CandidateAnswer.objects.get(session_id=sid2, question__index=0)
    assert ans.audio_file and ans.audio_duration_seconds == 12 and ans.transcript_source == "browser"
    url = hr_client.get(f"/api/interviews/{sid2}/answers/{ans.pk}/audio-url/").data["url"]
    assert anon.get(url).status_code == 200
    assert anon.get("/api/files/audio/forged/").status_code == 404
    assert cc2.get(f"/api/interviews/{sid2}/answers/{ans.pk}/audio-url/").status_code == 403


def test_evaluation_scoring_with_real_provider_contract(hr_client, approved, monkeypatch):
    """The 0-10 score is computed server-side from criterion scores; unverifiable evidence is dropped."""
    from apps.interviews.services import evaluation

    sid = approved[0]
    cc = candidate_client(invite(hr_client, sid))
    start(cc, sid)
    fake = FakeClient([{
        "criteria": {"relevance": 6, "reasoning": 5, "examples": 4, "correctness": 8, "job_alignment": 2},
        "positive_points": ["Knows tokens"], "missing_points": ["Signatures"], "inaccuracies": [], "suggestions": ["Explain expiry"],
        "feedback": "Basic knowledge.", "confidence": 0.9,
        "evidence": [{"quote": "jwt authentication", "supports": "correctness"}, {"quote": "this text is not in the answer", "supports": "x"}],
    }])
    monkeypatch.setattr(evaluation, "get_client", lambda org: fake)
    # question 1 is behavioral: weights relevance 30 / reasoning 25 / examples 30 / job_alignment 15
    q = cc.get(f"/api/interviews/{sid}/question/").data["question"]
    cc.post(f"/api/interviews/{sid}/answer/", {"question_id": q["id"], "text": ANSWER}, format="json")
    ev = AnswerEvaluation.objects.get(answer__session_id=sid, answer__question__index=0)
    assert float(ev.score) == pytest.approx(0.30 * 6 + 0.25 * 5 + 0.30 * 4 + 0.15 * 2, abs=0.01)
    assert [e["quote"] for e in ev.evidence] == ["jwt authentication"]
    assert ev.provider == "fake:fake-1" and not ev.is_mock
    # technical question uses 40/25/20/15
    for _ in range(4):  # move to Q6 (index 5) = first technical
        q = cc.get(f"/api/interviews/{sid}/question/").data["question"]
        monkeypatch.setattr(evaluation, "get_client", lambda org: FakeClient([{"criteria": {"relevance": 5, "reasoning": 5, "examples": 5, "job_alignment": 5, "correctness": 5}, "feedback": "", "confidence": 0.5}]))
        cc.post(f"/api/interviews/{sid}/answer/", {"question_id": q["id"], "text": ANSWER}, format="json")
    q = cc.get(f"/api/interviews/{sid}/question/").data["question"]
    assert q["number"] == 6
    monkeypatch.setattr(evaluation, "get_client", lambda org: FakeClient([{"criteria": {"correctness": 8, "relevance": 6, "reasoning": 5, "examples": 4}, "feedback": "x", "confidence": 0.8}]))
    cc.post(f"/api/interviews/{sid}/answer/", {"question_id": q["id"], "text": ANSWER}, format="json")
    ev = AnswerEvaluation.objects.get(answer__session_id=sid, answer__question__index=5)
    assert float(ev.score) == pytest.approx(6.3, abs=0.01)


def test_provider_failure_does_not_block_candidate_and_is_retried(hr_client, approved, monkeypatch):
    from apps.ai.errors import AIProviderError
    from apps.interviews.services import evaluation
    from apps.interviews.tasks import retry_failed_evaluations

    sid = approved[0]
    cc = candidate_client(invite(hr_client, sid))
    start(cc, sid)

    class Boom:
        is_mock = False

        def complete_json(self, *a, **k):
            raise AIProviderError("provider down")

    monkeypatch.setattr(evaluation, "get_client", lambda org: Boom())
    q = cc.get(f"/api/interviews/{sid}/question/").data["question"]
    r = cc.post(f"/api/interviews/{sid}/answer/", {"question_id": q["id"], "text": ANSWER}, format="json")
    assert r.status_code == 201 and r.data["progress"]["current_number"] == 2  # candidate continues
    ev = AnswerEvaluation.objects.get(answer__session_id=sid)
    assert ev.status == "failed" and ev.score is None
    monkeypatch.undo()
    assert retry_failed_evaluations(sid) == 1
    assert AnswerEvaluation.objects.get(answer__session_id=sid).status == "completed"


def test_results_hidden_unless_hr_enables(hr_client, approved):
    sid = approved[0]
    cc = candidate_client(invite(hr_client, sid))
    start(cc, sid)
    q = cc.get(f"/api/interviews/{sid}/question/").data["question"]
    assert "feedback" not in cc.post(f"/api/interviews/{sid}/answer/", {"question_id": q["id"], "text": ANSWER}, format="json").data
    assert cc.get(f"/api/interviews/{sid}/results/").status_code == 403
    assert hr_client.patch(f"/api/interviews/{sid}/", {"reveal_results": True}, format="json").data["reveal_results"] is True
    q = cc.get(f"/api/interviews/{sid}/question/").data["question"]
    assert "feedback" in cc.post(f"/api/interviews/{sid}/answer/", {"question_id": q["id"], "text": ANSWER}, format="json").data
