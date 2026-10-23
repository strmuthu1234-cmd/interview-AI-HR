import logging

from celery import shared_task

from .models import AnswerEvaluation, InterviewSession
from .services import evaluation, questions, scoring

log = logging.getLogger(__name__)


@shared_task
def generate_questions_task(session_id):
    session = InterviewSession.objects.select_related("candidate", "job", "organization").get(pk=session_id)
    return questions.run_generation(session)


@shared_task
def retry_failed_evaluations(session_id=None):
    """Re-run evaluations that failed because the provider was unavailable."""
    qs = AnswerEvaluation.objects.filter(status=AnswerEvaluation.Status.FAILED).select_related(
        "answer__question", "answer__session__job", "answer__session__organization")
    if session_id:
        qs = qs.filter(answer__session_id=session_id)
    n = 0
    for ev in qs[:200]:
        new = evaluation.evaluate_answer(ev.answer)
        n += new.status == AnswerEvaluation.Status.COMPLETED
    return n


@shared_task
def generate_report_task(session_id):
    session = InterviewSession.objects.select_related("candidate", "job", "organization", "analysis").get(pk=session_id)
    retry_failed_evaluations(str(session.pk))
    return str(scoring.build_report(session).pk)
