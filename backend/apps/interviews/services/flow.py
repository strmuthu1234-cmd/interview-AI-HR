"""Server-side interview state machine.

The backend - not React - decides which question is active. A question can only
be answered when it is the session's current question; the next one unlocks only
after the answer is saved AND an evaluation attempt has been recorded. Pauses or
silence never advance the interview.
"""
import logging

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.defaults import get_org_settings
from apps.recruitment.models import Candidate

from ..models import TOTAL_QUESTIONS, AnswerEvaluation, CandidateAnswer, InterviewInvitation, InterviewSession, PendingAudio
from . import evaluation

log = logging.getLogger(__name__)


class FlowError(Exception):
    def __init__(self, code, message, status=409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def accept_instructions(session, recording_consent: bool):
    with transaction.atomic():
        s = InterviewSession.objects.select_for_update().get(pk=session.pk)
        if s.status not in (s.Status.READY, s.Status.IN_PROGRESS):
            raise FlowError("not_ready", "This interview is not available to start.")
        now = timezone.now()
        if s.instructions_accepted_at is None:
            s.instructions_accepted_at = now
            s.recording_consent = bool(recording_consent)
            s.consent_at = now
        s.status = s.Status.IN_PROGRESS
        s.started_at = s.started_at or now
        s.save()
        Candidate.objects.filter(pk=s.candidate_id, status=Candidate.Status.INTERVIEW_INVITED).update(status=Candidate.Status.INTERVIEWING)
        InterviewInvitation.objects.filter(session=s).exclude(status="completed").update(status="opened", opened_at=s.started_at)
    return s


def _require_in_progress(s):
    if s.status != s.Status.IN_PROGRESS or s.instructions_accepted_at is None:
        raise FlowError("not_started", "Please accept the interview instructions first.")


def active_question(session):
    session.refresh_from_db()
    _require_in_progress(session)
    if session.current_index >= TOTAL_QUESTIONS:
        return None
    q = session.questions.get(index=session.current_index)
    if hasattr(q, "answer"):  # answered but not yet unlocked (e.g. connection dropped mid-request): recover
        finalize_current(session.pk)
        session.refresh_from_db()
        if session.current_index >= TOTAL_QUESTIONS:
            return None
        q = session.questions.get(index=session.current_index)
    return q


def finalize_current(session_id):
    """Evaluate the current question's answer if needed, then unlock the next question."""
    s = InterviewSession.objects.get(pk=session_id)
    if s.current_index >= TOTAL_QUESTIONS:
        return s
    q = s.questions.get(index=s.current_index)
    ans = CandidateAnswer.objects.filter(question=q).select_related("question", "session__job", "session__organization").first()
    if ans is None:
        return s
    if not AnswerEvaluation.objects.filter(answer=ans).exists():
        try:
            evaluation.evaluate_answer(ans)
        except IntegrityError:  # concurrent finaliser already created it
            pass
    with transaction.atomic():
        s = InterviewSession.objects.select_for_update().get(pk=session_id)
        if s.current_index == q.index:
            s.current_index += 1
            s.save(update_fields=["current_index"])
    return s


def submit_answer(session, *, question_id, text="", input_mode="text", client_submission_id="", skip=False, transcript_source=""):
    """Save an answer for the ACTIVE question, evaluate it, unlock the next. Idempotent per client_submission_id."""
    text = (text or "").strip()
    if len(text) > settings.MAX_ANSWER_CHARS:
        raise FlowError("too_long", f"Answer is too long (max {settings.MAX_ANSWER_CHARS} characters).", 400)
    if not skip and not text:
        raise FlowError("empty_answer", "Please provide an answer, or choose to skip this question.", 400)
    if input_mode not in ("text", "voice"):
        raise FlowError("bad_mode", "input_mode must be 'text' or 'voice'.", 400)

    with transaction.atomic():
        s = InterviewSession.objects.select_for_update().get(pk=session.pk)
        _require_in_progress(s)
        if client_submission_id:
            dup = CandidateAnswer.objects.filter(session=s, client_submission_id=client_submission_id).first()
            if dup:
                finalize_current(s.pk)
                return dup, True
        if s.current_index >= TOTAL_QUESTIONS:
            raise FlowError("all_answered", "All questions have already been answered.")
        q = s.questions.get(index=s.current_index)
        if str(q.id) != str(question_id):
            raise FlowError("wrong_question", "This is not the active question. Reload to continue where you left off.")
        if CandidateAnswer.objects.filter(question=q).exists():
            raise FlowError("already_answered", "This question was already answered.")
        pending = PendingAudio.objects.filter(question=q).first()
        answer = CandidateAnswer(
            session=s, question=q, text="" if skip else text, input_mode=input_mode, client_submission_id=client_submission_id or "",
            status=CandidateAnswer.Status.UNAVAILABLE if skip else CandidateAnswer.Status.SUBMITTED,
            transcript_source=("typed" if input_mode == "text" else (transcript_source or (pending.transcript_source if pending else "") or "browser")),
        )
        if pending and input_mode == "voice" and s.recording_consent and not skip:
            answer.audio_file.name = pending.audio_file.name  # keep stored file, drop the pending row
            answer.audio_duration_seconds = pending.duration_seconds
        elif pending:
            pending.audio_file.delete(save=False)  # no consent or typed answer: discard recording
        if pending:
            PendingAudio.objects.filter(pk=pending.pk).delete()
        answer.save()
    finalize_current(session.pk)  # evaluate (outside the lock) and unlock next
    return answer, False


def complete(session):
    with transaction.atomic():
        s = InterviewSession.objects.select_for_update().get(pk=session.pk)
        if s.status == s.Status.COMPLETED:
            return s, False
        _require_in_progress(s)
        if s.current_index < TOTAL_QUESTIONS or s.answers.count() < TOTAL_QUESTIONS:
            raise FlowError("incomplete", "All 20 questions must be answered before submitting the interview.")
        now = timezone.now()
        s.status, s.completed_at = s.Status.COMPLETED, now
        s.duration_seconds = int((now - (s.started_at or now)).total_seconds())
        s.save()
        InterviewInvitation.objects.filter(session=s).update(status="completed")
        Candidate.objects.filter(pk=s.candidate_id).update(status=Candidate.Status.INTERVIEWED)
    return s, True


def progress(session):
    session.refresh_from_db()
    answered = session.answers.count()
    return {
        "status": session.status,
        "total": TOTAL_QUESTIONS,
        "answered": answered,
        "current_number": min(session.current_index + 1, TOTAL_QUESTIONS),
        "all_answered": session.current_index >= TOTAL_QUESTIONS,
        "completed": session.status == session.Status.COMPLETED,
        "instructions_accepted": session.instructions_accepted_at is not None,
        "recording_consent": session.recording_consent,
    }


def candidate_settings(session):
    s = get_org_settings(session.organization)
    return {"max_answer_seconds": s["interview"]["max_answer_seconds"], "allow_pause": s["voice"]["allow_pause"],
            "language": session.language, "languages": s["voice"]["languages"], "stt_provider": s["voice"]["stt_provider"]}
